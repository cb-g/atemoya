"""
Retry utilities with exponential backoff.

This module provides retry logic for handling transient failures,
particularly useful for API calls and database operations.
"""

import random
import time
from typing import TypeVar, Callable, Optional

T = TypeVar('T')


def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = 5,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    retryable_errors: Optional[list[str]] = None
) -> T:
    """
    Retry a function with exponential backoff.

    Handles transient errors like database locks and API rate limits
    that occur when multiple processes access shared resources.

    Args:
        func: Zero-argument callable to execute
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay after each retry
        retryable_errors: List of error substrings that trigger retry.
                         If None, uses default list for yfinance errors.

    Returns:
        The return value of func() on success

    Raises:
        The last exception if all retries fail, or immediately for
        non-retryable errors.
    """
    if retryable_errors is None:
        retryable_errors = [
            "UNIQUE constraint failed: _cookieschema",
            "database is locked",
            "Connection reset",
            "Read timed out",
        ]

    delay = initial_delay
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_error = e
            error_msg = str(e)

            # Check if error is retryable
            is_retryable = any(err in error_msg for err in retryable_errors)

            if is_retryable and attempt < max_retries - 1:
                # Add jitter to avoid thundering herd
                jitter = random.uniform(0, delay * 0.3)
                sleep_time = delay + jitter
                delay *= backoff_factor
                time.sleep(sleep_time)
            else:
                # Non-retryable error or last attempt
                raise

    # Should never reach here, but satisfy type checker
    if last_error:
        raise last_error
    raise RuntimeError("Retry logic failed unexpectedly")
