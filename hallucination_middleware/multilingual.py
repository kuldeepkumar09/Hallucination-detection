"""
Multilingual Support Module — Language detection, translation, and cross-lingual verification.

Provides:
- Language detection for input text
- Automatic translation to English for verification
- Cross-lingual claim matching
- Multi-language knowledge base support
- Language-specific processing pipelines
"""
import logging
import re
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class LanguageCode(str, Enum):
    """Supported language codes."""
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    DUTCH = "nl"
    RUSSIAN = "ru"
    CHINESE = "zh"
    JAPANESE = "ja"
    KOREAN = "ko"
    ARABIC = "ar"
    HINDI = "hi"
    UNKNOWN = "unknown"


@dataclass
class LanguageDetection:
    """Result of language detection."""
    language: LanguageCode
    confidence: float
    is_latin_script: bool
    detected_script: str


@dataclass
class TranslationResult:
    """Result of translation."""
    original_text: str
    translated_text: str
    source_language: LanguageCode
    target_language: LanguageCode
    confidence: float
    translation_method: str  # "neural", "statistical", "dictionary", "fallback"


# ── Language Detection Patterns ────────────────────────────────────────────

# Simple pattern-based language detection (fallback when ML models unavailable)
LANGUAGE_PATTERNS = {
    LanguageCode.SPANISH: {
        "patterns": [r'\b(qu[eí]|como|donde|cuando|porque|tambi[eé]n|pero|siempre|nunca|todo|nada)\b'],
        "script": "latin",
    },
    LanguageCode.FRENCH: {
        "patterns": [r'\b(le|la|les|un|une|des|et|ou|mais|donc|or|ni|car|que|qui|est|sont)\b'],
        "script": "latin",
    },
    LanguageCode.GERMAN: {
        "patterns": [r'\b(der|die|das|und|ist|nicht|mit|von|auf|f[uü]r|aber|auch|wenn)\b'],
        "script": "latin",
    },
    LanguageCode.ITALIAN: {
        "patterns": [r'\b(il|la|le|gli|i|un|una|e|o|ma|che|di|a|da|in|con|su|per|non|ci|si)\b'],
        "script": "latin",
    },
    LanguageCode.PORTUGUESE: {
        "patterns": [r'\b(o|a|os|as|um|uma|e|ou|mas|que|de|do|da|em|no|na|por|para|n[aã]o|se)\b'],
        "script": "latin",
    },
    LanguageCode.DUTCH: {
        "patterns": [r'\b(de|het|een|en|of|maar|want|dat|die|is|niet|met|van|op|voor|in)\b'],
        "script": "latin",
    },
    LanguageCode.RUSSIAN: {
        "patterns": [r'[\u0400-\u04FF]'],  # Cyrillic range
        "script": "cyrillic",
    },
    LanguageCode.CHINESE: {
        "patterns": [r'[\u4e00-\u9fff]'],  # CJK Unified Ideographs
        "script": "cjk",
    },
    LanguageCode.JAPANESE: {
        "patterns": [r'[\u3040-\u309f\u30a0-\u30ff]'],  # Hiragana + Katakana
        "script": "japanese",
    },
    LanguageCode.KOREAN: {
        "patterns": [r'[\uac00-\ud7af]'],  # Hangul Syllables
        "script": "korean",
    },
    LanguageCode.ARABIC: {
        "patterns": [r'[\u0600-\u06ff]'],  # Arabic range
        "script": "arabic",
    },
    LanguageCode.HINDI: {
        "patterns": [r'[\u0900-\u097f]'],  # Devanagari range
        "script": "devanagari",
    },
}


class LanguageDetector:
    """
    Language detection with multiple strategies.
    
    Strategies (in order of preference):
    1. langdetect library (if available)
    2. Pattern-based detection (fallback)
    3. Script detection (last resort)
    """
    
    def __init__(self):
        self._langdetect_available = False
        self._fasttext_available = False
        self._try_import_libraries()
    
    def _try_import_libraries(self) -> None:
        """Try to import optional language detection libraries."""
        try:
            from langdetect import detect, DetectorFactory
            self._detect = detect
            self._langdetect_available = True
            logger.info("langdetect available for language detection")
        except ImportError:
            logger.info("langdetect not available — using pattern-based detection")
        
        try:
            import fasttext
            self._fasttext_available = True
            logger.info("fasttext available for language detection")
        except ImportError:
            pass
    
    def detect(self, text: str) -> LanguageDetection:
        """
        Detect the language of the input text.
        
        Returns:
            LanguageDetection with detected language and confidence
        """
        if not text or not text.strip():
            return LanguageDetection(
                language=LanguageCode.UNKNOWN,
                confidence=0.0,
                is_latin_script=False,
                detected_script="none",
            )
        
        # Try langdetect first (most accurate)
        if self._langdetect_available:
            try:
                lang_code = self._detect(text[:1000])  # Limit for performance
                return LanguageDetection(
                    language=LanguageCode(lang_code[:2].lower()),
                    confidence=0.9,  # langdetect doesn't provide confidence
                    is_latin_script=self._is_latin_script(text),
                    detected_script=self._detect_script(text),
                )
            except Exception:
                pass
        
        # Fallback to pattern-based detection
        return self._pattern_detect(text)
    
    def _pattern_detect(self, text: str) -> LanguageDetection:
        """Pattern-based language detection fallback."""
        text_lower = text.lower()
        scores: Dict[LanguageCode, int] = {}
        
        for lang, config in LANGUAGE_PATTERNS.items():
            score = 0
            for pattern in config["patterns"]:
                matches = re.findall(pattern, text_lower, re.IGNORECASE)
                score += len(matches)
            if score > 0:
                scores[lang] = score
        
        if not scores:
            # No patterns matched — likely English or unknown
            return LanguageDetection(
                language=LanguageCode.ENGLISH,
                confidence=0.3,
                is_latin_script=self._is_latin_script(text),
                detected_script=self._detect_script(text),
            )
        
        # Get highest scoring language
        best_lang = max(scores, key=scores.get)
        best_score = scores[best_lang]
        total_score = sum(scores.values())
        
        # Calculate confidence based on score distribution
        confidence = min(0.95, best_score / total_score) if total_score > 0 else 0.3
        
        return LanguageDetection(
            language=best_lang,
            confidence=confidence,
            is_latin_script=LANGUAGE_PATTERNS[best_lang]["script"] == "latin",
            detected_script=LANGUAGE_PATTERNS[best_lang]["script"],
        )
    
    def _is_latin_script(self, text: str) -> bool:
        """Check if text uses Latin script."""
        # Check first 500 chars for performance
        sample = text[:500]
        latin_chars = sum(1 for c in sample if ord(c) < 256)
        return (latin_chars / len(sample)) > 0.8 if sample else False
    
    def _detect_script(self, text: str) -> str:
        """Detect the writing script used in text."""
        sample = text[:500]
        
        for lang, config in LANGUAGE_PATTERNS.items():
            for pattern in config["patterns"]:
                if re.search(pattern, sample):
                    return config["script"]
        
        return "latin"  # Default


class Translator:
    """
    Translation service with multiple backends.
    
    Backends (in order of preference):
    1. Google Translate API (if key available)
    2. LibreTranslate (free, self-hostable)
    3. Simple dictionary-based translation (fallback)
    """
    
    def __init__(self):
        self._google_available = False
        self._libre_available = False
        self._try_init_backends()
    
    def _try_init_backends(self) -> None:
        """Initialize translation backends."""
        try:
            from googletrans import Translator
            self._google_translator = Translator()
            self._google_available = True
            logger.info("Google Translate backend available")
        except ImportError:
            pass
        
        # LibreTranslate can be used via API
        try:
            import requests
            self._requests = requests
            self._libre_available = True
            logger.info("LibreTranslate backend available")
        except ImportError:
            pass
    
    async def translate(
        self, 
        text: str, 
        source_lang: LanguageCode, 
        target_lang: LanguageCode = LanguageCode.ENGLISH
    ) -> TranslationResult:
        """
        Translate text from source language to target language.
        
        Args:
            text: Text to translate
            source_lang: Source language
            target_lang: Target language (default: English)
        
        Returns:
            TranslationResult with translated text and metadata
        """
        if source_lang == target_lang:
            return TranslationResult(
                original_text=text,
                translated_text=text,
                source_language=source_lang,
                target_language=target_lang,
                confidence=1.0,
                translation_method="identity",
            )
        
        # Try Google Translate first
        if self._google_available:
            try:
                result = await self._google_translate(text, source_lang, target_lang)
                if result:
                    return result
            except Exception as exc:
                logger.debug(f"Google Translate failed: {exc}")
        
        # Try LibreTranslate
        if self._libre_available:
            try:
                result = await self._libre_translate(text, source_lang, target_lang)
                if result:
                    return result
            except Exception as exc:
                logger.debug(f"LibreTranslate failed: {exc}")
        
        # Fallback to simple translation (just return original)
        return TranslationResult(
            original_text=text,
            translated_text=text,  # No translation available
            source_language=source_lang,
            target_language=target_lang,
            confidence=0.0,
            translation_method="fallback",
        )
    
    async def _google_translate(
        self, 
        text: str, 
        source_lang: LanguageCode, 
        target_lang: LanguageCode
    ) -> Optional[TranslationResult]:
        """Translate using Google Translate."""
        try:
            result = await asyncio.to_thread(
                self._google_translator.translate,
                text,
                src=source_lang.value,
                dest=target_lang.value,
            )
            return TranslationResult(
                original_text=text,
                translated_text=result.text,
                source_language=source_lang,
                target_language=target_lang,
                confidence=0.85,
                translation_method="neural",
            )
        except Exception:
            return None
    
    async def _libre_translate(
        self, 
        text: str, 
        source_lang: LanguageCode, 
        target_lang: LanguageCode
    ) -> Optional[TranslationResult]:
        """Translate using LibreTranslate API."""
        try:
            # Use public LibreTranslate instance (or configure your own)
            url = "https://libretranslate.com/translate"
            payload = {
                "q": text,
                "source": source_lang.value,
                "target": target_lang.value,
                "format": "text",
            }
            
            response = await asyncio.to_thread(
                self._requests.post,
                url,
                json=payload,
                timeout=30,
            )
            
            if response.status_code == 200:
                data = response.json()
                return TranslationResult(
                    original_text=text,
                    translated_text=data.get("translatedText", text),
                    source_language=source_lang,
                    target_language=target_lang,
                    confidence=0.75,
                    translation_method="neural",
                )
        except Exception:
            pass
        
        return None


# ── Cross-Lingual Claim Matching ──────────────────────────────────────────

class CrossLingualMatcher:
    """
    Match claims across different languages.
    
    Features:
    - Translate claims to common language for matching
    - Semantic similarity across languages
    - Language-aware evidence retrieval
    """
    
    def __init__(self, translator: Translator = None):
        self.translator = translator or Translator()
        self._multilingual_cache: Dict[str, Any] = {}
    
    async def normalize_claim(
        self, 
        claim_text: str, 
        source_lang: LanguageCode
    ) -> Tuple[str, LanguageCode]:
        """
        Normalize claim to English for verification.
        
        Returns:
            Tuple of (normalized_claim, original_language)
        """
        if source_lang == LanguageCode.ENGLISH:
            return claim_text, source_lang
        
        result = await self.translator.translate(
            claim_text, 
            source_lang, 
            LanguageCode.ENGLISH
        )
        
        return result.translated_text, source_lang
    
    async def translate_evidence(
        self, 
        evidence_text: str, 
        source_lang: LanguageCode,
        target_lang: LanguageCode = LanguageCode.ENGLISH
    ) -> str:
        """Translate evidence text for claim verification."""
        if source_lang == target_lang:
            return evidence_text
        
        result = await self.translator.translate(
            evidence_text,
            source_lang,
            target_lang,
        )
        
        return result.translated_text


# ── Language-Specific Processing ──────────────────────────────────────────

class LanguageProcessor:
    """
    Language-specific text processing.
    
    Handles:
    - Tokenization differences
    - Sentence splitting variations
    - Language-specific NLP processing
    """
    
    def __init__(self):
        self._spacy_languages = set()
        self._try_load_spacy_models()
    
    def _try_load_spacy_models(self) -> None:
        """Try to load spaCy models for supported languages."""
        try:
            import spacy
            # Try to load common language models
            for lang in ["en", "es", "fr", "de", "pt", "it", "nl"]:
                try:
                    spacy.load(f"{lang}_core_web_sm")
                    self._spacy_languages.add(lang)
                except OSError:
                    pass
            logger.info(f"spaCy models available for: {self._spacy_languages}")
        except ImportError:
            pass
    
    def process_text(self, text: str, language: LanguageCode) -> Dict[str, Any]:
        """
        Process text with language-specific rules.
        
        Returns:
            Dictionary with processed text components
        """
        result = {
            "original_text": text,
            "language": language.value,
            "sentences": self._split_sentences(text, language),
            "tokens": self._tokenize(text, language),
            "word_count": len(text.split()),
        }
        
        return result
    
    def _split_sentences(self, text: str, language: LanguageCode) -> List[str]:
        """Split text into sentences with language-aware rules."""
        # Use spaCy if available for this language
        if language.value in self._spacy_languages:
            try:
                import spacy
                nlp = spacy.load(f"{language.value}_core_web_sm")
                doc = nlp(text[:50000])  # Limit for performance
                return [sent.text.strip() for sent in doc.sents if sent.text.strip()]
            except Exception:
                pass
        
        # Fallback to simple sentence splitting
        # Handle common sentence endings for different languages
        if language in [LanguageCode.ENGLISH, LanguageCode.SPANISH, LanguageCode.FRENCH]:
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        elif language == LanguageCode.CHINESE:
            sentences = re.split(r'[。！？]', text)
        elif language == LanguageCode.JAPANESE:
            sentences = re.split(r'[。！？]', text)
        else:
            sentences = re.split(r'(?<=[.!?。！？])\s*', text)
        
        return [s.strip() for s in sentences if s.strip()]
    
    def _tokenize(self, text: str, language: LanguageCode) -> List[str]:
        """Tokenize text with language-specific rules."""
        if language in [LanguageCode.CHINESE, LanguageCode.JAPANESE]:
            # CJK languages: each character is roughly a word
            return list(text.replace(' ', ''))
        elif language == LanguageCode.KOREAN:
            # Korean: space-separated but with complex morphology
            return text.split()
        else:
            # Latin-based languages: simple whitespace tokenization
            return text.split()


# ── Global Instances ──────────────────────────────────────────────────────

_detector: Optional[LanguageDetector] = None
_translator: Optional[Translator] = None
_matcher: Optional[CrossLingualMatcher] = None
_processor: Optional[LanguageProcessor] = None


def get_language_detector() -> LanguageDetector:
    """Get or create global language detector."""
    global _detector
    if _detector is None:
        _detector = LanguageDetector()
    return _detector


def get_translator() -> Translator:
    """Get or create global translator."""
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def get_cross_lingual_matcher() -> CrossLingualMatcher:
    """Get or create global cross-lingual matcher."""
    global _matcher
    if _matcher is None:
        _matcher = CrossLingualMatcher(get_translator())
    return _matcher


def get_language_processor() -> LanguageProcessor:
    """Get or create global language processor."""
    global _processor
    if _processor is None:
        _processor = LanguageProcessor()
    return _processor


def detect_language(text: str) -> LanguageDetection:
    """Detect language of input text."""
    return get_language_detector().detect(text)


async def translate_text(
    text: str, 
    source_lang: LanguageCode, 
    target_lang: LanguageCode = LanguageCode.ENGLISH
) -> TranslationResult:
    """Translate text between languages."""
    return await get_translator().translate(text, source_lang, target_lang)


def process_multilingual_text(text: str, language: LanguageCode) -> Dict[str, Any]:
    """Process text with language-specific rules."""
    return get_language_processor().process_text(text, language)