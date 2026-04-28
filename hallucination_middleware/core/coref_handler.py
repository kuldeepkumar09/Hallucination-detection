"""Coreference Resolution — replaces pronouns with explicit referents before claim extraction.

Example: "Einstein was born in Ulm. He won the Nobel Prize."
      → "Einstein was born in Ulm. Einstein won the Nobel Prize."

Primary path  : coreferee spaCy extension (neural, accurate — requires coreferee installed).
Fallback path : rule-based NER + token-position resolver using spaCy 3.7.x built-ins.
                Works without any extra package; catches the most common pronoun patterns.

The fallback handles:
  he/him/his/himself          → nearest preceding PERSON entity
  she/her/hers/herself        → nearest preceding PERSON entity
  they/them/their/themselves  → nearest preceding entity of any type
  it/its/itself               → nearest preceding entity of any type
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_nlp = None
_has_coreferee = False

# Pronouns resolved by the NER fallback, mapped to preferred entity label
# (None = accept any entity type)
_PRONOUN_TARGET: dict[str, Optional[str]] = {
    "he":         "PERSON",
    "him":        "PERSON",
    "his":        "PERSON",
    "himself":    "PERSON",
    "she":        "PERSON",
    "her":        "PERSON",
    "hers":       "PERSON",
    "herself":    "PERSON",
    "they":       None,
    "them":       None,
    "their":      None,
    "theirs":     None,
    "themselves": None,
    "it":         None,
    "its":        None,
    "itself":     None,
}

_POSSESSIVES = {"his", "her", "hers", "its", "their", "theirs"}


def _get_nlp():
    global _nlp, _has_coreferee
    if _nlp is not None:
        return _nlp
    try:
        import spacy
        import coreferee  # noqa: F401
        _nlp = spacy.load("en_core_web_sm")
        _nlp.add_pipe("coreferee")
        _has_coreferee = True
        logger.info("[coref] coreferee loaded — neural coreference active")
    except Exception as exc:
        logger.info("[coref] coreferee unavailable (%s) — using NER+dep fallback", exc)
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except Exception:
            _nlp = None
    return _nlp


def _resolve_ner_fallback(doc, text: str) -> str:
    """
    Rule-based pronoun resolver using spaCy NER.

    For each third-person pronoun, finds the nearest *preceding* named entity of
    the expected type and substitutes the entity text.  Possessive forms (his/its/…)
    get an apostrophe-s suffix.

    Limitations (acknowledged): no sentence-boundary awareness, no syntactic binding.
    This is intentionally simple — the goal is to help the claim extractor, not to
    achieve production-grade coref accuracy.
    """
    # Build sorted entity list: (token_index, entity_text, entity_label)
    entity_seq = [(ent.start, ent.text, ent.label_) for ent in doc.ents]
    if not entity_seq:
        return text  # nothing to resolve

    # {char_start: (char_end, replacement_text)}
    replacements: dict[int, tuple[int, str]] = {}

    for token in doc:
        lower = token.lower_
        if lower not in _PRONOUN_TARGET:
            continue
        target_type = _PRONOUN_TARGET[lower]

        # Find nearest preceding entity of the right type within a 2-sentence window.
        # 60-token lookback ≈ 2–3 sentences; prevents cross-paragraph entity leakage.
        best: Optional[str] = None
        for ent_tok_i, ent_text, ent_label in reversed(entity_seq):
            if ent_tok_i >= token.i:
                continue  # must precede the pronoun
            if token.i - ent_tok_i > 60:
                break  # too far back — stop searching
            if target_type is None or ent_label == target_type:
                best = ent_text
                break

        if best is None:
            continue

        replacement = (best + "'s") if lower in _POSSESSIVES else best

        # Preserve sentence-initial capitalisation
        if token.text[0].isupper():
            replacement = replacement[0].upper() + replacement[1:]

        replacements[token.idx] = (token.idx + len(token.text), replacement)

    if not replacements:
        return text

    # Apply from right → left to keep earlier char positions valid
    result = list(text)
    for char_start in sorted(replacements, reverse=True):
        char_end, repl = replacements[char_start]
        result[char_start:char_end] = list(repl)

    resolved = "".join(result)
    logger.debug("[coref] NER fallback: resolved %d pronoun(s)", len(replacements))
    return resolved


def resolve_coreferences(text: str) -> str:
    """
    Main entry point.  Replace pronouns with their referents.

    Never raises — returns original text on any error.
    Primary: coreferee neural chains.
    Fallback: NER-based rule resolver (always runs when coreferee absent).
    """
    if not text.strip():
        return text

    nlp = _get_nlp()
    if nlp is None:
        return text

    try:
        doc = nlp(text[:50_000])

        # ── Primary: coreferee neural coref ─────────────────────────────────
        if _has_coreferee:
            chains = getattr(doc._, "coref_chains", None)
            if chains:
                replacements: dict[int, tuple[int, str]] = {}
                for chain in chains:
                    if not chain:
                        continue
                    main_mention = chain[0]
                    main_text = doc[main_mention[0]: main_mention[-1] + 1].text
                    for mention in chain[1:]:
                        span = doc[mention[0]: mention[-1] + 1]
                        if span.text.lower() in _PRONOUN_TARGET:
                            replacements[span.start_char] = (len(span.text), main_text)

                if replacements:
                    result = list(text)
                    for idx in sorted(replacements, reverse=True):
                        length, replacement = replacements[idx]
                        result[idx: idx + length] = list(replacement)
                    resolved = "".join(result)
                    logger.debug("[coref] coreferee: resolved %d chain mention(s)", len(replacements))
                    return resolved
            # coreferee loaded but found no chains — fall through to NER resolver
            return _resolve_ner_fallback(doc, text)

        # ── Fallback: NER+dep rule resolver ──────────────────────────────────
        return _resolve_ner_fallback(doc, text)

    except Exception as exc:
        logger.debug("[coref] resolution failed: %s", exc)
        return text
