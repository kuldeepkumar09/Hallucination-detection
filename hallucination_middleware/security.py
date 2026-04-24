"""
Security Module — Input sanitization, adversarial protection, and security utilities.

Provides:
- Input validation and sanitization
- Prompt injection detection
- Rate limiting enhancements
- PII detection and redaction
- Audit logging for security events
"""
import re
import logging
import hashlib
import json
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    """Threat level for security analysis."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityAnalysis:
    """Result of security analysis on input text."""
    threat_level: ThreatLevel
    threats_detected: List[str]
    sanitized_text: str
    original_length: int
    sanitized_length: int
    pii_detected: bool
    injection_detected: bool


# ── Prompt Injection Patterns ──────────────────────────────────────────────

INJECTION_PATTERNS = [
    # Direct instruction overrides
    r"(?i)ignore\s+(previous|all\s+previous|the\s+above)\s+(instructions|rules|content)",
    r"(?i)forget\s+(all\s+)?(previous|above|instructions)",
    r"(?i)do\s+not\s+(follow|obey|adhere\s+to)\s+(your|the)\s+(instructions|rules|guidelines)",
    r"(?i)override\s+(your|the)\s+(programming|instructions|rules)",
    r"(?i)bypass\s+(all|content|safety)\s+(filters|restrictions|rules)",
    
    # Role-playing attacks
    r"(?i)act\s+as\s+(a\s+)?(new\s+)?(assistant|ai|model|bot)",
    r"(?i)you\s+are\s+now\s+(in\s+)?(developer|debug|test|safe)\s+mode",
    r"(?i)pretend\s+to\s+be\s+(a\s+)?(different\s+)?(ai|assistant|model)",
    
    # Encoding/obfuscation attempts
    r"(?i)(decode|decrypt|interpret)\s+(this|the\s+following)\s+(base64|hex|encoded|obfuscated)",
    r"(?i)read\s+(the\s+)?(following|this)\s+(text|content)\s+backwards",
    
    # System prompt extraction
    r"(?i)what\s+(are\s+)?your\s+(instructions|rules|system\s+prompt|guidelines)",
    r"(?i)repeat\s+(your\s+)?(instructions|system\s+prompt|rules)",
    r"(?i)print\s+(your\s+)?(system\s+message|instructions|prompt)",
    
    # Logical paradoxes
    r"(?i)this\s+statement\s+is\s+false",
    r"(?i)ignore\s+this\s+sentence",
    
    # Command injection patterns
    r"(?i)(execute|run|eval)\s+(this|the\s+following)\s+(code|command|script)",
    r"(?i)<\s*script\s*>",
    r"(?i)javascript\s*:",
]

# ── PII Patterns ───────────────────────────────────────────────────────────

PII_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "phone_us": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    "ssn": r'\b\d{3}[-]?\d{2}[-]?\d{4}\b',
    "credit_card": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
    "ip_address": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
    "date_of_birth": r'\b(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01])/(?:19|20)\d{2}\b',
    "medical_id": r'\b[A-Z]{1,2}\d{6,8}\b',  # Generic medical ID pattern
}

# ── Malicious Content Patterns ─────────────────────────────────────────────

MALICIOUS_PATTERNS = [
    # SQL injection
    r"(?i)(union\s+select|drop\s+table|insert\s+into|delete\s+from|update\s+.*\s+set)",
    r"(?i)('|\"|;|--)",
    
    # XSS patterns
    r"(?i)<script[^>]*>.*?</script>",
    r"(?i)javascript\s*:",
    r"(?i)on(load|error|click|mouseover)\s*=",
    
    # Path traversal
    r"(?i)(\.\./|\.\.\\)",
    
    # Command injection
    r"(?i)[;&|`$]",
]


class SecurityValidator:
    """
    Comprehensive security validator for user inputs.
    
    Features:
    - Prompt injection detection
    - PII detection and redaction
    - Malicious content detection
    - Input length validation
    - Character encoding validation
    """
    
    def __init__(self, max_input_length: int = 50000):
        self.max_input_length = max_input_length
        self._compile_patterns()
        
    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance."""
        self._injection_regex = [re.compile(p) for p in INJECTION_PATTERNS]
        self._pii_regex = {name: re.compile(pattern) for name, pattern in PII_PATTERNS.items()}
        self._malicious_regex = [re.compile(p) for p in MALICIOUS_PATTERNS]
        
    def validate(self, text: str) -> Tuple[bool, str]:
        """
        Validate input text for security issues.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not text or not text.strip():
            return False, "Input text is empty"
            
        if len(text) > self.max_input_length:
            return False, f"Input exceeds maximum length of {self.max_input_length:,} characters"
            
        # Check for binary content
        if self._contains_binary(text):
            return False, "Input contains binary or non-text content"
            
        return True, ""
    
    def analyze(self, text: str) -> SecurityAnalysis:
        """
        Perform comprehensive security analysis on input text.
        
        Returns:
            SecurityAnalysis with threat level and detected issues
        """
        threats = []
        pii_detected = False
        injection_detected = False
        
        # Check for prompt injection
        for i, pattern in enumerate(self._injection_regex):
            if pattern.search(text):
                injection_detected = True
                threats.append(f"Prompt injection pattern detected (rule {i+1})")
        
        # Check for PII
        pii_types = []
        for name, pattern in self._pii_regex.items():
            if pattern.search(text):
                pii_detected = True
                pii_types.append(name)
                threats.append(f"PII detected: {name}")
        
        # Check for malicious content
        for i, pattern in enumerate(self._malicious_regex):
            if pattern.search(text):
                threats.append(f"Malicious content pattern detected (rule {i+1})")
        
        # Sanitize text
        sanitized = self._sanitize_text(text)
        
        # Determine threat level
        threat_level = self._calculate_threat_level(
            len(threats), injection_detected, pii_detected
        )
        
        return SecurityAnalysis(
            threat_level=threat_level,
            threats_detected=threats,
            sanitized_text=sanitized,
            original_length=len(text),
            sanitized_length=len(sanitized),
            pii_detected=pii_detected,
            injection_detected=injection_detected,
        )
    
    def sanitize(self, text: str) -> str:
        """Sanitize text by removing/redacting sensitive content."""
        sanitized = text
        
        # Redact PII
        for name, pattern in self._pii_regex.items():
            if name == "email":
                sanitized = pattern.sub("[EMAIL_REDACTED]", sanitized)
            elif name == "phone_us":
                sanitized = pattern.sub("[PHONE_REDACTED]", sanitized)
            elif name == "ssn":
                sanitized = pattern.sub("[SSN_REDACTED]", sanitized)
            elif name == "credit_card":
                sanitized = pattern.sub("[CARD_REDACTED]", sanitized)
            elif name == "ip_address":
                sanitized = pattern.sub("[IP_REDACTED]", sanitized)
            elif name == "date_of_birth":
                sanitized = pattern.sub("[DOB_REDACTED]", sanitized)
            elif name == "medical_id":
                sanitized = pattern.sub("[MEDICAL_ID_REDACTED]", sanitized)
        
        # Remove potential injection patterns
        for pattern in self._injection_regex:
            sanitized = pattern.sub("[INJECTION_REMOVED]", sanitized)
        
        # Remove malicious patterns
        for pattern in self._malicious_regex:
            sanitized = pattern.sub("", sanitized)
        
        return sanitized.strip()
    
    def _sanitize_text(self, text: str) -> str:
        """Internal sanitization method."""
        return self.sanitize(text)
    
    def _contains_binary(self, text: str) -> bool:
        """Check if text contains binary/non-printable characters."""
        if not text:
            return False
        # Check first 1000 chars for performance
        sample = text[:1000]
        non_printable = sum(1 for c in sample if ord(c) < 32 and c not in '\n\r\t')
        return (non_printable / len(sample)) > 0.05  # 5% threshold
    
    def _calculate_threat_level(
        self, 
        threat_count: int, 
        injection_detected: bool, 
        pii_detected: bool
    ) -> ThreatLevel:
        """Calculate overall threat level based on detected issues."""
        if injection_detected:
            return ThreatLevel.HIGH
        
        if pii_detected and threat_count > 2:
            return ThreatLevel.HIGH
        
        if pii_detected or threat_count > 3:
            return ThreatLevel.MEDIUM
        
        if threat_count > 0:
            return ThreatLevel.LOW
        
        return ThreatLevel.NONE
    
    def get_security_report(self, text: str) -> Dict[str, Any]:
        """Generate a comprehensive security report for the input."""
        is_valid, error = self.validate(text)
        analysis = self.analyze(text)
        
        return {
            "valid": is_valid,
            "validation_error": error,
            "threat_level": analysis.threat_level.value,
            "threats_detected": analysis.threats_detected,
            "threat_count": len(analysis.threats_detected),
            "pii_detected": analysis.pii_detected,
            "injection_detected": analysis.injection_detected,
            "original_length": analysis.original_length,
            "sanitized_length": analysis.sanitized_length,
            "reduction_percent": round(
                (1 - analysis.sanitized_length / analysis.original_length) * 100, 1
            ) if analysis.original_length > 0 else 0,
        }


# ── Global Security Validator ──────────────────────────────────────────────

_security_validator: Optional[SecurityValidator] = None


def get_security_validator() -> SecurityValidator:
    """Get or create the global security validator."""
    global _security_validator
    if _security_validator is None:
        _security_validator = SecurityValidator()
    return _security_validator


def validate_input(text: str) -> Tuple[bool, str]:
    """Validate input using global security validator."""
    return get_security_validator().validate(text)


def analyze_security(text: str) -> SecurityAnalysis:
    """Analyze security of input using global validator."""
    return get_security_validator().analyze(text)


def sanitize_input(text: str) -> str:
    """Sanitize input using global security validator."""
    return get_security_validator().sanitize(text)


def get_security_report(text: str) -> Dict[str, Any]:
    """Get comprehensive security report for input."""
    return get_security_validator().get_security_report(text)