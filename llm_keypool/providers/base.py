from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompletionResult:
    text: str
    tokens_used: int
    was_429: bool
    error: Optional[str] = None
    remaining_requests: Optional[int] = None
    rate_limit_headers: dict = field(default_factory=dict)
