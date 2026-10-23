import re


_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|password|passwd|secret|token|authorization)\b(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+")


def safe_excerpt(text: str, limit: int = 1000) -> str:
    """Keep citations useful while preventing obvious secrets from leaving controlled storage."""
    value = _BEARER.sub("Bearer [REDACTED]", text)
    return _ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)[:limit]
