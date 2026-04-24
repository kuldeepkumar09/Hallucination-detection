"""
Circuit Breaker Pattern — prevents cascading failures when LLM providers are down.

Implements the classic circuit breaker pattern with three states:
- CLOSED: Normal operation, requests pass through
- OPEN: Provider is failing, requests fail fast
- HALF_OPEN: Testing if provider has recovered

After N consecutive failures, circuit trips to OPEN state.
After a cooldown period, circuit transitions to HALF_OPEN to test recovery.
"""
import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5        # Failures before opening circuit
    success_threshold: int = 2        # Successes before closing circuit
    timeout: float = 60.0             # Seconds to wait before half-open
    expected_exceptions: tuple = (Exception,)  # Exceptions that count as failures
    fallback: Optional[Callable] = None  # Fallback function when circuit is open


class CircuitBreaker:
    """
    Circuit breaker for LLM provider resilience.
    
    Usage:
        cb = CircuitBreaker("ollama", CircuitBreakerConfig())
        result = await cb.call(llm_function, *args, **kwargs)
    """
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
        self.total_fallbacks = 0
        self._lock = asyncio.Lock()
        
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            self.total_calls += 1
            
            # Check if we should transition from OPEN to HALF_OPEN
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    logger.info(f"[{self.name}] Circuit breaker transitioning to HALF_OPEN")
                else:
                    self.total_fallbacks += 1
                    logger.warning(f"[{self.name}] Circuit OPEN — failing fast")
                    if self.config.fallback:
                        return await self._execute_fallback(*args, **kwargs)
                    raise CircuitBreakerOpenError(f"Circuit breaker open for {self.name}")
        
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except self.config.expected_exceptions as exc:
            await self._on_failure(exc)
            raise
    
    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            self.total_successes += 1
            self.failure_count = 0
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    logger.info(f"[{self.name}] Circuit breaker CLOSED — provider recovered")
            else:
                self.success_count = 0
    
    async def _on_failure(self, exc: Exception) -> None:
        """Handle failed call."""
        async with self._lock:
            self.total_failures += 1
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning(f"[{self.name}] Circuit breaker OPEN — recovery failed")
            elif self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                logger.error(f"[{self.name}] Circuit breaker OPEN — {self.failure_count} consecutive failures")
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        elapsed = time.monotonic() - self.last_failure_time
        return elapsed >= self.config.timeout
    
    async def _execute_fallback(self, *args, **kwargs) -> Any:
        """Execute fallback function if available."""
        try:
            if asyncio.iscoroutinefunction(self.config.fallback):
                return await self.config.fallback(*args, **kwargs)
            return self.config.fallback(*args, **kwargs)
        except Exception as exc:
            logger.error(f"[{self.name}] Fallback failed: {exc}")
            raise
    
    def get_stats(self) -> dict:
        """Return circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "total_calls": self.total_calls,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "total_fallbacks": self.total_fallbacks,
            "last_failure_time": self.last_failure_time,
        }
    
    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        logger.info(f"[{self.name}] Circuit breaker manually reset")


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and no fallback is available."""
    pass


# Global circuit breakers for different LLM providers
_circuit_breakers: dict = {}


def get_circuit_breaker(provider: str) -> CircuitBreaker:
    """Get or create circuit breaker for a provider."""
    if provider not in _circuit_breakers:
        config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=2,
            timeout=60.0,
        )
        _circuit_breakers[provider] = CircuitBreaker(provider, config)
    return _circuit_breakers[provider]


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers (useful for testing or manual intervention)."""
    for cb in _circuit_breakers.values():
        cb.reset()


def get_all_stats() -> dict:
    """Get stats for all circuit breakers."""
    return {name: cb.get_stats() for name, cb in _circuit_breakers.items()}