from __future__ import annotations

from dataclasses import dataclass

TIER_PRIORITY = "priority"
TIER_NORMAL = "normal"
TIER_MANUAL = "manual"


@dataclass(frozen=True)
class RefreshResult:
    """一次群资料刷新尝试的结果。"""

    group_id: str
    tier: str
    ok: bool
    platform_ids: list[str]
    started_at: float
    finished_at: float
    member_count: int | None = None
    message: str = ""
