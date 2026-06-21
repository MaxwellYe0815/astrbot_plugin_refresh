from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .config import RefreshConfig
from .models import RefreshResult, TIER_MANUAL
from .onebot_client import OneBotClient
from .scheduler import RefreshScheduler
from .storage import RefreshStorage


class RefreshService:
    def __init__(
        self,
        context: Any,
        *,
        data_dir: Path,
        runtime_config: dict[str, Any] | None = None,
    ) -> None:
        self.context = context
        self.data_dir = data_dir
        self.runtime_config = runtime_config if runtime_config is not None else {}
        self.config = RefreshConfig.from_mapping(runtime_config)
        self.storage = RefreshStorage(data_dir / "refresh_state.json")
        self.onebot = OneBotClient(context, self.config)
        self.scheduler = RefreshScheduler(self.config, self.storage)
        self.stop_event = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.tick_lock = asyncio.Lock()

    async def start(self) -> None:
        await self.storage.load()
        self.stop_event.clear()
        if self.config.enabled:
            self.task = asyncio.create_task(self._loop(), name="astrbot_plugin_refresh")
            logger.info("astrbot_plugin_refresh service started")
        else:
            logger.info("astrbot_plugin_refresh is disabled by config")

    async def stop(self) -> None:
        self.stop_event.set()
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None
        await self.storage.save()

    async def _loop(self) -> None:
        await self._sleep_or_stop(self.config.startup_delay_seconds)
        while not self.stop_event.is_set():
            try:
                await self.run_due_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"refresh: scheduled tick failed: {exc}", exc_info=True)
            await self._sleep_or_stop(self._loop_sleep_seconds())

    async def _sleep_or_stop(self, seconds: int | float) -> None:
        if seconds <= 0:
            return
        try:
            await asyncio.wait_for(self.stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    def _loop_sleep_seconds(self) -> int:
        interval = min(
            self.config.priority_interval_seconds,
            self.config.normal_interval_seconds,
        )
        return max(15, min(60, interval // 6 or 15))

    async def run_due_once(self) -> list[RefreshResult]:
        if not self.config.enabled:
            return []
        async with self.tick_lock:
            targets = self.scheduler.due_targets()
            results: list[RefreshResult] = []
            seen: set[str] = set()
            for group_id, tier in targets:
                if group_id in seen:
                    continue
                seen.add(group_id)
                result = await self.refresh_group(group_id, tier=tier)
                results.append(result)
            await self.storage.save()
            return results

    async def refresh_group(self, group_id: str, *, tier: str = TIER_MANUAL) -> RefreshResult:
        group_id = str(group_id).strip()
        started_at = time.time()
        try:
            platform_ids, member_count = await self.onebot.refresh_group_members(group_id)
            result = RefreshResult(
                group_id=group_id,
                tier=tier,
                ok=True,
                platform_ids=platform_ids,
                started_at=started_at,
                finished_at=time.time(),
                member_count=member_count,
                message="ok",
            )
            logger.info(
                f"refresh: group {group_id} refreshed via {platform_ids}, "
                f"members={member_count}",
            )
        except Exception as exc:
            result = RefreshResult(
                group_id=group_id,
                tier=tier,
                ok=False,
                platform_ids=[],
                started_at=started_at,
                finished_at=time.time(),
                message=str(exc),
            )
            logger.warning(f"refresh: group {group_id} refresh failed: {exc}")
        self.storage.apply_result(result)
        await self.storage.save()
        return result

    async def status_text(self) -> str:
        platforms = self.onebot.platforms()
        lines = [
            "refresh 状态",
            f"启用: {'是' if self.config.enabled else '否'}",
            f"OneBot 平台: {', '.join(p.platform_id for p in platforms) if platforms else '未找到'}",
            f"重点群: {len(self.config.priority_groups)} 个，每 {self.config.priority_interval_seconds} 秒刷新",
            (
                f"普通群: {len(self.config.normal_groups)} 个，每 "
                f"{self.config.normal_interval_seconds} 秒刷新 "
                f"{self.config.normal_groups_per_interval} 个"
            ),
            f"普通群游标: {self.storage.normal_cursor()}",
            f"上次普通群轮询: {_format_time(self.storage.last_normal_run_at())}",
        ]

        groups = self.storage.state.get("groups") or {}
        recent = sorted(
            (
                (str(group_id), state)
                for group_id, state in groups.items()
                if isinstance(state, dict)
            ),
            key=lambda item: float(item[1].get("last_finished_at") or 0),
            reverse=True,
        )[:8]
        if recent:
            lines.append("最近刷新:")
            for group_id, state in recent:
                ok = not state.get("last_error")
                count = state.get("last_member_count")
                count_text = f", 成员 {count}" if count is not None else ""
                error_text = "" if ok else f", 错误 {state.get('last_error')}"
                lines.append(
                    f"- {group_id} [{state.get('tier') or 'unknown'}] "
                    f"{'成功' if ok else '失败'} "
                    f"{_format_time(state.get('last_finished_at'))}"
                    f"{count_text}{error_text}"
                )
        return "\n".join(lines)

    async def list_text(self) -> str:
        lines = ["refresh 群组配置"]
        lines.append(_format_group_line("重点群", self.config.priority_groups))
        lines.append(_format_group_line("普通群", self.config.normal_groups))
        return "\n".join(lines)

    async def add_group(self, group_id: str, *, priority: bool = False) -> tuple[bool, str]:
        group_id = _normalize_group_id(group_id)
        if not group_id:
            return False, "群号不能为空。"

        priority_groups = list(self.config.priority_groups)
        normal_groups = list(self.config.normal_groups)
        if priority:
            changed = _remove_group(normal_groups, group_id)
            if group_id not in priority_groups:
                priority_groups.append(group_id)
                changed = True
            tier = "重点群"
        else:
            changed = _remove_group(priority_groups, group_id)
            if group_id not in normal_groups:
                normal_groups.append(group_id)
                changed = True
            tier = "普通群"

        await self._save_group_config(priority_groups, normal_groups)
        if changed:
            return True, f"已设为{tier}: {group_id}"
        return False, f"无需变更，已经是{tier}: {group_id}"

    async def remove_group(self, group_id: str) -> tuple[bool, str]:
        group_id = _normalize_group_id(group_id)
        priority_groups = list(self.config.priority_groups)
        normal_groups = list(self.config.normal_groups)
        changed = _remove_group(priority_groups, group_id)
        changed = _remove_group(normal_groups, group_id) or changed
        await self._save_group_config(priority_groups, normal_groups)
        if changed:
            return True, f"已移除群 {group_id}"
        return False, f"群 {group_id} 不在刷新名单中"

    async def _save_group_config(
        self,
        priority_groups: list[str],
        normal_groups: list[str],
    ) -> None:
        priority_groups = _unique_groups(priority_groups)
        priority_set = set(priority_groups)
        normal_groups = [
            group_id for group_id in _unique_groups(normal_groups) if group_id not in priority_set
        ]
        self.runtime_config["priority_groups"] = priority_groups
        self.runtime_config["normal_groups"] = normal_groups
        save_config = getattr(self.runtime_config, "save_config", None)
        if callable(save_config):
            save_config()

        self.config = RefreshConfig.from_mapping(self.runtime_config)
        self.onebot = OneBotClient(self.context, self.config)
        self.scheduler = RefreshScheduler(self.config, self.storage)


def _format_group_line(label: str, groups: list[str]) -> str:
    if not groups:
        return f"{label}: 空"
    preview = ", ".join(groups[:20])
    if len(groups) > 20:
        preview += f", ... 共 {len(groups)} 个"
    return f"{label}: {preview}"


def _format_time(value: Any) -> str:
    try:
        timestamp = float(value or 0)
    except (TypeError, ValueError):
        timestamp = 0
    if timestamp <= 0:
        return "无"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_group_id(value: Any) -> str:
    return str(value or "").strip()


def _unique_groups(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        group_id = _normalize_group_id(value)
        if not group_id or group_id in seen:
            continue
        seen.add(group_id)
        result.append(group_id)
    return result


def _remove_group(groups: list[str], group_id: str) -> bool:
    changed = False
    while group_id in groups:
        groups.remove(group_id)
        changed = True
    return changed
