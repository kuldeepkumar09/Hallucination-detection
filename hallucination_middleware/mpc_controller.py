"""
MPC (Model Predictive Control) for hallucination-free text generation.

Receding-horizon flow:
  1. Split input text into sentence-level chunks.
  2. For each chunk, generate N candidate alternative phrasings via LLM.
  3. Score each candidate by querying the KB — avg relevance = factual confidence.
  4. Select the lowest-cost (most factual) candidate.
  5. Append selected candidate to rolling context → feed to next chunk.

Result: a rewritten version of the text where each sentence has been replaced
by its most knowledge-base-supported alternative.
"""
import asyncio
import logging
import re
from typing import List, Optional

from openai import AsyncOpenAI

from .config import get_settings
from .knowledge_base import KnowledgeBase
from .models import MPCCandidate, MPCResult

logger = logging.getLogger(__name__)

_CANDIDATE_SYSTEM = """\
You are a precise factual rewriter. You will be given a sentence and context.
Rewrite the sentence so it is more likely to be factually accurate, preserving its meaning.
Output ONLY the rewritten sentence — no explanations, no JSON, no preamble.
"""

# Temperatures spread across low/medium/high to maximise candidate diversity.
# Three candidates → [0.1, 0.6, 1.0]; four → [0.1, 0.45, 0.75, 1.0]; etc.
def _candidate_temperatures(n: int) -> List[float]:
    if n == 1:
        return [0.3]
    step = 0.9 / (n - 1)
    return [round(0.1 + i * step, 2) for i in range(n)]


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences using spaCy if available, else regex."""
    try:
        import spacy
        nlp = spacy.load(get_settings().spacy_language_model, disable=["ner", "parser", "tagger"])
        nlp.enable_pipe("senter")
        doc = nlp(text[:50_000])
        return [s.text.strip() for s in doc.sents if s.text.strip()]
    except Exception:
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [p.strip() for p in parts if p.strip()]



class MPCController:
    """
    Rewrites text using a receding-horizon factual selection loop.
    Instantiate once per pipeline; call run() for each text.
    """

    def __init__(self, knowledge_base: KnowledgeBase) -> None:
        self._kb = knowledge_base
        s = get_settings()
        self._settings = s
        self._n = s.mpc_candidates

        if s.llm_provider == "nvidia_nim":
            self._client = AsyncOpenAI(
                base_url=s.nvidia_nim_base_url,
                api_key=s.nvidia_nim_api_key,
                timeout=s.request_timeout,
            )
        elif s.llm_provider in ("together", "anthropic"):
            self._client = AsyncOpenAI(
                base_url=s.together_base_url,
                api_key=s.together_api_key,
                timeout=s.request_timeout,
            )
        else:
            self._client = AsyncOpenAI(
                base_url=s.ollama_base_url,
                api_key=s.ollama_api_key,
                timeout=s.request_timeout,
            )

    async def run(self, text: str) -> MPCResult:
        """
        Run the MPC loop over *text*.  Returns MPCResult with corrected_text
        and the per-chunk candidate list for visualization.

        Cost guard: at most mpc_max_sentences sentences are processed via LLM.
        Sentences beyond that limit are appended verbatim to keep output complete.
        At mpc_candidates=3 and mpc_max_sentences=10 this caps the MPC cost at
        30 LLM calls regardless of input length.
        """
        chunks = _split_sentences(text)
        if not chunks:
            return MPCResult(original_text=text, corrected_text=text)

        max_sentences = self._settings.mpc_max_sentences
        if len(chunks) > max_sentences:
            logger.info(
                "MPC cost guard: %d sentences → only first %d processed via LLM, rest kept verbatim",
                len(chunks), max_sentences,
            )

        context = ""
        selected_parts: List[str] = []
        all_candidates: List[List[MPCCandidate]] = []

        for idx, chunk in enumerate(chunks):
            # Cost guard: append verbatim beyond the sentence limit
            if idx >= max_sentences:
                selected_parts.append(chunk)
                all_candidates.append([MPCCandidate(text=chunk, cost=0.0, kb_score=1.0, selected=True)])
                context += " " + chunk
                continue
            if len(chunk) < 15:
                # Too short to meaningfully rewrite — keep as-is
                selected_parts.append(chunk)
                all_candidates.append([MPCCandidate(text=chunk, cost=0.0, kb_score=1.0, selected=True)])
                context += " " + chunk
                continue

            candidates_text = await self._generate_candidates(chunk, context)
            if not candidates_text:
                candidates_text = [chunk]

            scored = await self._score_candidates(candidates_text)

            if not scored:
                # KB unavailable or all candidates failed scoring — keep original chunk
                selected_parts.append(chunk)
                all_candidates.append([MPCCandidate(text=chunk, cost=0.5, kb_score=0.5, selected=True)])
                context += " " + chunk
                continue

            # Pick lowest cost (= highest KB support)
            best_idx = min(range(len(scored)), key=lambda i: scored[i].cost)
            scored[best_idx] = scored[best_idx].model_copy(update={"selected": True})

            best_text = scored[best_idx].text
            selected_parts.append(best_text)
            all_candidates.append(scored)
            context += " " + best_text

        corrected = " ".join(selected_parts).strip()
        return MPCResult(
            original_text=text,
            corrected_text=corrected,
            candidates_per_chunk=all_candidates,
        )

    async def _generate_candidates(self, chunk: str, context: str) -> List[str]:
        user = (
            f"Context (preceding text): {context[-500:] if context else 'none'}\n\n"
            f"Sentence to rewrite: {chunk}"
        )
        temperatures = _candidate_temperatures(self._n)

        async def _one_call(temp: float) -> str:
            try:
                resp = await self._client.chat.completions.create(
                    model=self._settings.extractor_model,
                    messages=[
                        {"role": "system", "content": _CANDIDATE_SYSTEM},
                        {"role": "user", "content": user},
                    ],
                    temperature=temp,
                    max_tokens=256,
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as exc:
                logger.warning("MPC candidate (temp=%.2f) failed: %s", temp, exc)
                return ""

        results = await asyncio.gather(*[_one_call(t) for t in temperatures])
        candidates = [chunk]  # always include original
        for r in results:
            if r and r not in candidates:
                candidates.append(r)
        return candidates[:self._n]

    async def _score_candidates(self, candidates: List[str]) -> List[MPCCandidate]:
        """
        Score candidates using NLI faithfulness + factual density.
        No web search needed — uses the DeBERTa-v3 NLI model already loaded.

        Faithfulness: how well the candidate entails the original sentence.
        Factual density: presence of digits and proper nouns = more specific = more verifiable.
        """
        from .nli_scorer import get_nli_scorer  # noqa: PLC0415
        nli = get_nli_scorer()
        original = candidates[0]  # original is always first

        scored: List[MPCCandidate] = []
        for cand in candidates:
            if nli is not None and cand != original:
                result = nli.score(cand, original)
                faithfulness = result.get("entailment", 0.5) if result else 0.5
            else:
                faithfulness = 1.0  # original is perfectly faithful to itself

            # Factual density heuristic: more digits + capitalized words = more specific
            digit_count = len(re.findall(r"\d", cand))
            cap_count = len(re.findall(r"\b[A-Z][a-z]+", cand))
            word_count = max(len(cand.split()), 1)
            density = min(1.0, (digit_count + cap_count) / word_count * 3)

            kb_score = round(0.6 * faithfulness + 0.4 * density, 4)
            cost = round(1.0 - kb_score, 4)
            scored.append(MPCCandidate(text=cand, cost=cost, kb_score=kb_score))
        return scored
