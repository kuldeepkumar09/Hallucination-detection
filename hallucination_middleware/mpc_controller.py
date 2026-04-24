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
Generate exactly {n} alternative phrasings of the sentence that preserve its meaning
but are more likely to be factually accurate. Each alternative must be a complete sentence.
Output ONLY a JSON array of strings, no explanations:
["alternative 1", "alternative 2", "alternative 3"]
"""


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


def _extract_string_list(content: str) -> List[str]:
    """Parse a JSON array of strings from LLM output."""
    import json
    content = re.sub(r"```(?:json)?\s*", "", content).replace("```", "").strip()
    # Find the array
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return [str(s).strip() for s in parsed if str(s).strip()]
        except json.JSONDecodeError:
            pass
    # Fallback: extract quoted strings
    items = re.findall(r'"([^"]+)"', content)
    return items


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
        system = _CANDIDATE_SYSTEM.format(n=self._n)
        user = (
            f"Context (preceding text): {context[-500:] if context else 'none'}\n\n"
            f"Sentence to rewrite: {chunk}\n\n"
            f"Generate {self._n} factual alternatives."
        )
        try:
            resp = await self._client.chat.completions.create(
                model=self._settings.verifier_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                max_tokens=512,
            )
            content = resp.choices[0].message.content or ""
            candidates = _extract_string_list(content)
            # Always include the original as one candidate
            if chunk not in candidates:
                candidates = [chunk] + candidates
            return candidates[:self._n]
        except Exception as exc:
            logger.warning("MPC candidate generation failed: %s", exc)
            return [chunk]

    async def _score_candidates(self, candidates: List[str]) -> List[MPCCandidate]:
        """Score each candidate by querying the KB — higher avg relevance = lower cost."""
        tasks = [self._kb.query_async(c, n_results=3) for c in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        scored: List[MPCCandidate] = []
        for cand, hits in zip(candidates, results):
            if isinstance(hits, Exception) or not hits:
                kb_score = 0.0
            else:
                kb_score = sum(h.get("relevance_score", 0.0) for h in hits) / len(hits)
            cost = round(1.0 - kb_score, 4)
            scored.append(MPCCandidate(text=cand, cost=cost, kb_score=round(kb_score, 4)))
        return scored
