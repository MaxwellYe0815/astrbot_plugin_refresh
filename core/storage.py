from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .models import RefreshResult


class RefreshStorage:
    """保存刷新状态，不保存任何群成员资料。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.state: dict[str, Any] = {
            "version": 1,
            "normal_cursor": 0,
            "last_normal_run_at": 0.0,
            "groups": {},
        }

    async def load(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            await self.save()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                f"refresh: failed to load state file, using empty state: {exc}"
            )
            return
        if isinstance(data, dict):
            self.state.update(data)
        # 状态文件被手动改坏时尽量自愈。
        if not isinstance(self.state.get("groups"), dict):
            self.state["groups"] = {}
        self.state.setdefault("normal_cursor", 0)
        self.state.setdefault("last_normal_run_at", 0.0)

    async def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 先写临时文件再替换，减少半写入状态。
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        text = json.dumps(self.state, ensure_ascii=False, indent=2, sort_keys=True)
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(self.path)

    def group_state(self, group_id: str) -> dict[str, Any]:
        groups = self.state.setdefault("groups", {})
        # 这里再兜底一次，防止运行中状态被外部改坏。
        if not isinstance(groups, dict):
            groups = {}
            self.state["groups"] = groups
        key = str(group_id)
        group_state = groups.get(key)
        if not isinstance(group_state, dict):
            group_state = {}
            groups[key] = group_state
        return group_state

    def last_normal_run_at(self) -> float:
        return _float_value(self.state.get("last_normal_run_at"))

    def mark_normal_run(self, timestamp: float) -> None:
        self.state["last_normal_run_at"] = float(timestamp)

    def normal_cursor(self) -> int:
        try:
            return int(self.state.get("normal_cursor") or 0)
        except (TypeError, ValueError):
            return 0

    def set_normal_cursor(self, value: int) -> None:
        self.state["normal_cursor"] = max(0, int(value))

    def apply_result(self, result: RefreshResult) -> None:
        """把一次刷新结果合并进对应群的状态。"""
        group_state = self.group_state(result.group_id)
        previous_fail_count = _int_value(group_state.get("fail_count"))
        group_state.update(
            {
                "tier": result.tier,
                "last_attempt_at": float(result.started_at),
                "last_finished_at": float(result.finished_at),
                "last_platform_ids": list(result.platform_ids),
            },
        )
        if result.ok:
            group_state.update(
                {
                    "last_success_at": float(result.finished_at),
                    "last_error": "",
                    "fail_count": 0,
                    "last_member_count": result.member_count,
                },
            )
        else:
            group_state.update(
                {
                    "last_error": result.message,
                    "fail_count": previous_fail_count + 1,
                },
            )


def _float_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
