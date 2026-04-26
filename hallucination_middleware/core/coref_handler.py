"""Coreference Resolution — replaces pronouns with explicit referents before claim extraction.

Example: "Einstein was born in Ulm. He won the Nobel Prize."
      → "Einstein was born in Ulm. Einstein won the Nobel Prize."

Uses coreferee (spaCy extension). Falls back gracefully if not installed.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_nlp = None
_has_coreferee = False


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
        logger.info("[coref] coreferee loaded on en_core_web_sm")
    except Exception as exc:
        logger.info("[coref] coreferee not available (%s) — using spaCy NER fallback", exc)
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except Exception:
            _nlp = None
    return _nlp


_PRONOUNS = {
    "he", "she", "it", "they", "his", "her", "its", "their",
    "him", "them", "himself", "herself", "itself", "themselves",
    "this", "that", "these", "those",
}


def resolve_coreferences(text: str) -> str:
    """Replace pronouns with their referents. Returns cleaned text.
    Never raises — returns original text on any error."""
    if not text.strip():
        return text

    nlp = _get_nlp()
    if nlp is None:
        return text

    try:
        doc = nlp(text[:50_000])

        if not _has_coreferee:
            return text

        if not hasattr(doc._, "coref_chains") or doc._.coref_chains is None:
            return text

        replacements: dict = {}
        for chain in doc._.coref_chains:
            if not chain:
                continue
            main_mention = chain[0]
            main_text = doc[main_mention[0]:main_mention[-1] + 1].text

            for mention in chain[1:]:
                mention_span = doc[mention[0]:mention[-1] + 1]
                mention_text = mention_span.text
                if mention_text.lower() in _PRONOUNS:
                    char_start = mention_span.start_char
                    replacements[char_start] = (len(mention_text), main_text)

        if not replacements:
            return text

        result = list(text)
        for idx in sorted(replacements.keys(), reverse=True):
            length, replacement = replacements[idx]
            result[idx:idx + length] = list(replacement)

        return "".join(result)

    except Exception as exc:
        logger.debug("[coref] resolution failed: %s", exc)
        return text
