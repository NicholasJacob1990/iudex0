"""
Resilience Patterns for RAG Storage Services

Provides circuit breaker and retry patterns for reliable storage operations:
- CircuitBreaker: Prevents cascading failures by failing fast when service is unhealthy
- Retry with exponential backoff: Handles transient failures gracefully
- Fallback behavior: Graceful degradation when circuit is open

States:
- CLOSED: Normal operation, requests flow through
- OPEN: Service unhealthy, requests fail fast (return fallback)
- HALF_OPEN: Testing if service recovered

Configuration via environment variables:
- CIRCUIT_FAILURE_THRESHOLD: Number of failures before opening (default: 5)
- CIRCUIT_RECOVERY_TIMEOUT: Seconds before attempting recovery (default: 60)
- RETRY_MAX_ATTEMPTS: Maximum retry attempts (default: 3)
- RETRY_BASE_DELAY: Base delay in seconds for exponential backoff (default: 1.0)
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generic, Optional, TypeVar, Union

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing fast
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5      # Failures before opening
    recovery_timeout: float = 60.0  # Seconds before testing recovery
    half_open_max_calls: int = 3    # Max calls in half-open state
    excluded_exceptions: tuple = () # Exceptions that don't count as failures

    @classmethod
    def from_env(cls, prefix: str = "CIRCUIT") -> "CircuitBreakerConfig":
        """Load configuration from environment variables."""
        return cls(
            failure_threshold=int(os.getenv(f"{prefix}_FAILURE_THRESHOLD", "5")),
            recovery_timeout=float(os.getenv(f"{prefix}_RECOVERY_TIMEOUT", "60")),
            half_open_max_calls=int(os.getenv(f"{prefix}_HALF_OPEN_MAX_CALLS", "3")),
        )


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker monitoring."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    last_state_change: Optional[float] = None
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    total_rejected: int = 0  # Calls rejected when circuit open

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "last_state_change": self.last_state_change,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "total_rejected": self.total_rejected,
        }


class CircuitBreaker:
    """
    Circuit breaker implementation for fault tolerance.

    Monitors failures and opens the circuit when threshold is exceeded,
    preventing further calls until the service recovers.

    Usage:
        breaker = CircuitBreaker("opensearch", config)

        @breaker
        def search(...):
            ...

        # Or manually:
        if breaker.allow_request():
            try:
                result = do_something()
                breaker.record_success()
            except Exception as e:
                breaker.record_failure(e)
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Identifier for this circuit (used in logging)
            config: Configuration options
        """
        self.name = name
        self.config = config or CircuitBreakerConfig.from_env()
        self._stats = CircuitBreakerStats()
        self._lock = threading.RLock()
        self._half_open_calls = 0

        logger.info(
            f"CircuitBreaker '{name}' initialized: "
            f"failure_threshold={self.config.failure_threshold}, "
            f"recovery_timeout={self.config.recovery_timeout}s"
        )

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._stats.state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Get current statistics."""
        return self._stats

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state with logging."""
        old_state = self._stats.state
        if old_state == new_state:
            return

        self._stats.state = new_state
        self._stats.last_state_change = time.time()

        if new_state == CircuitState.OPEN:
            logger.warning(
                f"CircuitBreaker '{self.name}': CLOSED -> OPEN "
                f"(failures={self._stats.failure_count})"
            )
        elif new_state == CircuitState.HALF_OPEN:
            logger.info(
                f"CircuitBreaker '{self.name}': OPEN -> HALF_OPEN "
                f"(testing recovery)"
            )
            self._half_open_calls = 0
        elif new_state == CircuitState.CLOSED:
            logger.info(
                f"CircuitBreaker '{self.name}': {old_state.value.upper()} -> CLOSED "
                f"(service recovered)"
            )
            self._stats.failure_count = 0
            self._stats.success_count = 0

    def allow_request(self) -> bool:
        """
        Check if a request should be allowed.

        Returns:
            True if request can proceed, False if circuit is open.
        """
        with self._lock:
            now = time.time()

            if self._stats.state == CircuitState.CLOSED:
                return True

            if self._stats.state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                if self._stats.last_failure_time is not None:
                    elapsed = now - self._stats.last_failure_time
                    if elapsed >= self.config.recovery_timeout:
                        self._transition_to(CircuitState.HALF_OPEN)
                        return True
                self._stats.total_rejected += 1
                return False

            if self._stats.state == CircuitState.HALF_OPEN:
                # Allow limited calls in half-open state
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

            return False

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self._stats.total_calls += 1
            self._stats.total_successes += 1
            self._stats.success_count += 1
            self._stats.last_success_time = time.time()

            if self._stats.state == CircuitState.HALF_OPEN:
                # After enough successes, close the circuit
                if self._stats.success_count >= self.config.half_open_max_calls:
                    self._transition_to(CircuitState.CLOSED)
            elif self._stats.state == CircuitState.CLOSED:
                # Reset failure count on success
                self._stats.failure_count = 0

    def record_failure(self, exception: Optional[Exception] = None) -> None:
        """Record a failed call."""
        with self._lock:
            # Check if this exception type should be excluded
            if exception and isinstance(exception, self.config.excluded_exceptions):
                logger.debug(
                    f"CircuitBreaker '{self.name}': Excluded exception {type(exception).__name__}"
                )
                return

            self._stats.total_calls += 1
            self._stats.total_failures += 1
            self._stats.failure_count += 1
            self._stats.last_failure_time = time.time()
            self._stats.success_count = 0  # Reset success count

            if self._stats.state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens the circuit
                self._transition_to(CircuitState.OPEN)
            elif self._stats.state == CircuitState.CLOSED:
                if self._stats.failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

            if exception:
                logger.warning(
                    f"CircuitBreaker '{self.name}': Failure recorded - {type(exception).__name__}: {exception}"
                )

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        with self._lock:
            self._stats = CircuitBreakerStats()
            self._half_open_calls = 0
            logger.info(f"CircuitBreaker '{self.name}': Reset to CLOSED")

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """
        Decorator to wrap a function with circuit breaker.

        Usage:
            @circuit_breaker
            def my_function():
                ...
        """
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            if not self.allow_request():
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is open"
                )
            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure(e)
                raise

        return wrapper


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and request is rejected."""
    pass


@dataclass
class RetryConfig:
    """Configuration for retry with exponential backoff."""
    max_attempts: int = 3
    base_delay: float = 1.0     # Base delay in seconds
    max_delay: float = 30.0     # Maximum delay cap
    exponential_base: float = 2.0
    jitter: bool = True         # Add randomness to prevent thundering herd
    retryable_exceptions: tuple = (Exception,)

    @classmethod
    def from_env(cls, prefix: str = "RETRY") -> "RetryConfig":
        """Load configuration from environment variables."""
        return cls(
            max_attempts=int(os.getenv(f"{prefix}_MAX_ATTEMPTS", "3")),
            base_delay=float(os.getenv(f"{prefix}_BASE_DELAY", "1.0")),
            max_delay=float(os.getenv(f"{prefix}_MAX_DELAY", "30.0")),
            exponential_base=float(os.getenv(f"{prefix}_EXPONENTIAL_BASE", "2.0")),
            jitter=os.getenv(f"{prefix}_JITTER", "true").lower() == "true",
        )


def calculate_backoff_delay(
    attempt: int,
    config: RetryConfig,
) -> float:
    """
    Calculate delay for exponential backoff.

    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration

    Returns:
        Delay in seconds
    """
    delay = config.base_delay * (config.exponential_base ** attempt)
    delay = min(delay, config.max_delay)

    if config.jitter:
        # Add random jitter (0-25% of delay)
        jitter_amount = delay * random.uniform(0, 0.25)
        delay += jitter_amount

    return delay


def retry_with_backoff(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retry with exponential backoff.

    Args:
        config: Retry configuration
        on_retry: Callback called before each retry (attempt, exception, delay)

    Usage:
        @retry_with_backoff(RetryConfig(max_attempts=3))
        def my_function():
            ...
    """
    _config = config or RetryConfig.from_env()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(_config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except _config.retryable_exceptions as e:
                    last_exception = e

                    if attempt == _config.max_attempts - 1:
                        # Last attempt, don't retry
                        break

                    delay = calculate_backoff_delay(attempt, _config)

                    if on_retry:
                        on_retry(attempt, e, delay)
                    else:
                        logger.warning(
                            f"Retry {attempt + 1}/{_config.max_attempts} for {func.__name__}: "
                            f"{type(e).__name__}: {e}. Waiting {delay:.2f}s"
                        )

                    time.sleep(delay)

            # All retries exhausted
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry exhausted without exception")

        return wrapper

    return decorator


async def retry_with_backoff_async(
    func: Callable[..., T],
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
    *args: Any,
    **kwargs: Any,
) -> T:
    """
    Async version of retry with exponential backoff.

    Args:
        func: Async function to call
        config: Retry configuration
        on_retry: Callback called before each retry
        *args, **kwargs: Arguments to pass to func

    Returns:
        Result of successful function call
    """
    _config = config or RetryConfig.from_env()
    last_exception: Optional[Exception] = None

    for attempt in range(_config.max_attempts):
        try:
            return await func(*args, **kwargs)
        except _config.retryable_exceptions as e:
            last_exception = e

            if attempt == _config.max_attempts - 1:
                break

            delay = calculate_backoff_delay(attempt, _config)

            if on_retry:
                on_retry(attempt, e, delay)
            else:
                logger.warning(
                    f"Async retry {attempt + 1}/{_config.max_attempts}: "
                    f"{type(e).__name__}: {e}. Waiting {delay:.2f}s"
                )

            await asyncio.sleep(delay)

    if last_exception:
        raise last_exception
    raise RuntimeError("Retry exhausted without exception")


class ResilientService(Generic[T]):
    """
    Base class for services with built-in resilience patterns.

    Combines circuit breaker and retry for robust service calls.

    Usage:
        class MyService(ResilientService):
            def __init__(self):
                super().__init__("my_service")

            def call_external(self):
                return self.execute_with_resilience(
                    self._actual_call,
                    fallback_value=[]
                )
    """

    def __init__(
        self,
        name: str,
        circuit_config: Optional[CircuitBreakerConfig] = None,
        retry_config: Optional[RetryConfig] = None,
    ):
        self.name = name
        self.circuit_breaker = CircuitBreaker(name, circuit_config)
        self.retry_config = retry_config or RetryConfig.from_env()
        self._fallback_enabled = True

    @property
    def is_healthy(self) -> bool:
        """Check if service is healthy (circuit not open)."""
        return self.circuit_breaker.state != CircuitState.OPEN

    @property
    def circuit_state(self) -> CircuitState:
        """Get current circuit state."""
        return self.circuit_breaker.state

    def get_health_status(self) -> Dict[str, Any]:
        """Get detailed health status."""
        return {
            "name": self.name,
            "healthy": self.is_healthy,
            "circuit_breaker": self.circuit_breaker.stats.to_dict(),
        }

    def execute_with_resilience(
        self,
        func: Callable[..., T],
        fallback_value: Optional[T] = None,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute a function with circuit breaker and retry.

        Args:
            func: Function to execute
            fallback_value: Value to return if circuit is open
            *args, **kwargs: Arguments for func

        Returns:
            Result of func or fallback_value
        """
        # Check circuit breaker first
        if not self.circuit_breaker.allow_request():
            if self._fallback_enabled and fallback_value is not None:
                logger.warning(
                    f"Circuit open for '{self.name}', returning fallback"
                )
                return fallback_value
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is open"
            )

        # Execute with retry
        last_exception: Optional[Exception] = None

        for attempt in range(self.retry_config.max_attempts):
            try:
                result = func(*args, **kwargs)
                self.circuit_breaker.record_success()
                return result
            except self.retry_config.retryable_exceptions as e:
                last_exception = e

                if attempt == self.retry_config.max_attempts - 1:
                    break

                delay = calculate_backoff_delay(attempt, self.retry_config)
                logger.warning(
                    f"Retry {attempt + 1}/{self.retry_config.max_attempts} "
                    f"for '{self.name}': {e}. Waiting {delay:.2f}s"
                )
                time.sleep(delay)

        # All retries failed
        if last_exception:
            self.circuit_breaker.record_failure(last_exception)

            if self._fallback_enabled and fallback_value is not None:
                logger.warning(
                    f"All retries failed for '{self.name}', returning fallback"
                )
                return fallback_value

            raise last_exception

        raise RuntimeError("Unexpected state in execute_with_resilience")

    async def execute_with_resilience_async(
        self,
        func: Callable[..., T],
        fallback_value: Optional[T] = None,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Async version of execute_with_resilience.

        Args:
            func: Async function to execute
            fallback_value: Value to return if circuit is open
            *args, **kwargs: Arguments for func

        Returns:
            Result of func or fallback_value
        """
        if not self.circuit_breaker.allow_request():
            if self._fallback_enabled and fallback_value is not None:
                logger.warning(
                    f"Circuit open for '{self.name}', returning fallback"
                )
                return fallback_value
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is open"
            )

        last_exception: Optional[Exception] = None

        for attempt in range(self.retry_config.max_attempts):
            try:
                result = await func(*args, **kwargs)
                self.circuit_breaker.record_success()
                return result
            except self.retry_config.retryable_exceptions as e:
                last_exception = e

                if attempt == self.retry_config.max_attempts - 1:
                    break

                delay = calculate_backoff_delay(attempt, self.retry_config)
                logger.warning(
                    f"Async retry {attempt + 1}/{self.retry_config.max_attempts} "
                    f"for '{self.name}': {e}. Waiting {delay:.2f}s"
                )
                await asyncio.sleep(delay)

        if last_exception:
            self.circuit_breaker.record_failure(last_exception)

            if self._fallback_enabled and fallback_value is not None:
                logger.warning(
                    f"All async retries failed for '{self.name}', returning fallback"
                )
                return fallback_value

            raise last_exception

        raise RuntimeError("Unexpected state in execute_with_resilience_async")


# =============================================================================
# Global Circuit Breaker Registry
# =============================================================================

_circuit_breakers: Dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None,
) -> CircuitBreaker:
    """
    Get or create a circuit breaker by name.

    Args:
        name: Circuit breaker name
        config: Configuration (used only if creating new)

    Returns:
        CircuitBreaker instance
    """
    with _registry_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name, config)
        return _circuit_breakers[name]


def get_all_circuit_breakers() -> Dict[str, CircuitBreaker]:
    """Get all registered circuit breakers."""
    with _registry_lock:
        return dict(_circuit_breakers)


def get_circuit_breaker_status() -> Dict[str, Dict[str, Any]]:
    """Get status of all circuit breakers."""
    with _registry_lock:
        return {
            name: breaker.stats.to_dict()
            for name, breaker in _circuit_breakers.items()
        }


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers to closed state."""
    with _registry_lock:
        for breaker in _circuit_breakers.values():
            breaker.reset()
        logger.info("All circuit breakers reset")


# =============================================================================
# Convenience Decorators
# =============================================================================


def with_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to add circuit breaker to a function.

    Args:
        name: Circuit breaker name
        config: Configuration

    Usage:
        @with_circuit_breaker("my_service")
        def call_external():
            ...
    """
    breaker = get_circuit_breaker(name, config)
    return breaker


def with_retry(
    config: Optional[RetryConfig] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to add retry with backoff to a function.

    Args:
        config: Retry configuration

    Usage:
        @with_retry(RetryConfig(max_attempts=3))
        def call_external():
            ...
    """
    return retry_with_backoff(config)


def with_resilience(
    name: str,
    circuit_config: Optional[CircuitBreakerConfig] = None,
    retry_config: Optional[RetryConfig] = None,
    fallback_value: Optional[T] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator combining circuit breaker and retry.

    Args:
        name: Circuit breaker name
        circuit_config: Circuit breaker configuration
        retry_config: Retry configuration
        fallback_value: Value to return on failure

    Usage:
        @with_resilience("my_service", fallback_value=[])
        def call_external():
            ...
    """
    breaker = get_circuit_breaker(name, circuit_config)
    _retry_config = retry_config or RetryConfig.from_env()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            if not breaker.allow_request():
                if fallback_value is not None:
                    logger.warning(
                        f"Circuit open for '{name}', returning fallback"
                    )
                    return fallback_value
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{name}' is open"
                )

            last_exception: Optional[Exception] = None

            for attempt in range(_retry_config.max_attempts):
                try:
                    result = func(*args, **kwargs)
                    breaker.record_success()
                    return result
                except _retry_config.retryable_exceptions as e:
                    last_exception = e

                    if attempt == _retry_config.max_attempts - 1:
                        break

                    delay = calculate_backoff_delay(attempt, _retry_config)
                    logger.warning(
                        f"Retry {attempt + 1}/{_retry_config.max_attempts} "
                        f"for '{name}': {e}. Waiting {delay:.2f}s"
                    )
                    time.sleep(delay)

            if last_exception:
                breaker.record_failure(last_exception)

                if fallback_value is not None:
                    logger.warning(
                        f"All retries failed for '{name}', returning fallback"
                    )
                    return fallback_value

                raise last_exception

            raise RuntimeError("Unexpected state")

        return wrapper

    return decorator
