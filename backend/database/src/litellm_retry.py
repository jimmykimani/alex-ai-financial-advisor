"""
Tenacity helpers for LiteLLM / Bedrock rate limits.

Daily token quotas should not be retried — retries only extend job "running" time and
make the UI feel stuck while every attempt fails the same way.
"""

try:
    from litellm.exceptions import RateLimitError
except ImportError:  # pragma: no cover - minimal typing fallback
    RateLimitError = Exception  # type: ignore[misc,assignment]


def retry_litellm_rate_limit_if_transient(exc: BaseException) -> bool:
    """
    Return True if this RateLimitError is worth retrying (e.g. short burst throttle).

    Return False for daily / fixed-window token caps where immediate retry cannot help.
    """
    if not isinstance(exc, RateLimitError):
        return False
    msg = str(exc).lower()
    if "tokens per day" in msg:
        return False
    if "too many tokens" in msg and "day" in msg:
        return False
    if "daily" in msg and ("quota" in msg or "limit" in msg):
        return False
    return True
