from __future__ import annotations

import hashlib
import time

from .config import RefreshConfig
from .models import TIER_NORMAL, TIER_PRIORITY
from .storage import RefreshStorage


class RefreshScheduler:
    def __init__(self, config: RefreshConfig, storage: RefreshStorage) -> None:
        self.config = config
        self.storage = storage

    def due_targets(self, now: float | None = None) -> list[tuple[str, str]]:
        now = time.time() if now is None else now
        targets: list[tuple[str, str]] = []

        for group_id in self.config.priority_groups:
            if self._priority_group_due(group_id, now):
                targets.append((group_id, TIER_PRIORITY))

        if self.config.normal_groups and self._normal_batch_due(now):
            for group_id in self._next_normal_batch():
                targets.append((group_id, TIER_NORMAL))
            self.storage.mark_normal_run(now)

        return targets

    def _priority_group_due(self, group_id: str, now: float) -> bool:
        state = self.storage.group_state(group_id)
        last_success_at = _float_value(state.get("last_success_at"))
        last_attempt_at = _float_value(state.get("last_attempt_at"))
        fail_count = int(state.get("fail_count") or 0)

        if fail_count > 0:
            backoff = min(3600, 60 * (2 ** min(fail_count - 1, 5)))
            if now - last_attempt_at < backoff:
                return False

        if last_success_at <= 0:
            return last_attempt_at <= 0 or fail_count > 0

        interval = self.config.priority_interval_seconds + self._stable_jitter(
            group_id,
            TIER_PRIORITY,
        )
        return now - last_success_at >= interval

    def _normal_batch_due(self, now: float) -> bool:
        last_run_at = self.storage.last_normal_run_at()
        return (
            last_run_at <= 0 or now - last_run_at >= self.config.normal_interval_seconds
        )

    def _next_normal_batch(self) -> list[str]:
        groups = self.config.normal_groups
        if not groups:
            return []

        per_interval = min(self.config.normal_groups_per_interval, len(groups))
        cursor = self.storage.normal_cursor() % len(groups)
        selected: list[str] = []
        for offset in range(per_interval):
            selected.append(groups[(cursor + offset) % len(groups)])
        self.storage.set_normal_cursor((cursor + per_interval) % len(groups))
        return selected

    def _stable_jitter(self, group_id: str, tier: str) -> int:
        jitter = self.config.jitter_seconds
        if jitter <= 0:
            return 0
        digest = hashlib.sha1(f"{tier}:{group_id}".encode()).digest()
        return int.from_bytes(digest[:4], "big") % (jitter + 1)


def _float_value(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
