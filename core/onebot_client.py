from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from astrbot.api import logger

from .config import RefreshConfig


ONEBOT_PLATFORM_NAMES = {"aiocqhttp"}


@dataclass(frozen=True)
class OneBotPlatform:
    platform_id: str
    platform_name: str
    client: Any


class OneBotClient:
    def __init__(self, context: Any, config: RefreshConfig) -> None:
        self.context = context
        self.config = config

    def platforms(self) -> list[OneBotPlatform]:
        manager = getattr(self.context, "platform_manager", None)
        get_insts = getattr(manager, "get_insts", None)
        if not callable(get_insts):
            return []

        platforms: list[OneBotPlatform] = []
        for platform in list(get_insts() or []):
            try:
                meta = platform.meta()
            except Exception as exc:
                logger.debug(f"refresh: skip platform without metadata: {exc}")
                continue

            platform_name = str(getattr(meta, "name", "") or "")
            if platform_name not in ONEBOT_PLATFORM_NAMES:
                continue

            get_client = getattr(platform, "get_client", None)
            if not callable(get_client):
                continue
            client = get_client()
            if not _has_call_action(client):
                continue

            platform_id = str(getattr(meta, "id", "") or platform_name)
            platforms.append(
                OneBotPlatform(
                    platform_id=platform_id,
                    platform_name=platform_name,
                    client=client,
                ),
            )
        return platforms

    async def refresh_group_members(self, group_id: str) -> tuple[list[str], int | None]:
        platforms = self.platforms()
        if not platforms:
            raise RuntimeError("未找到可用的 aiocqhttp / OneBot 平台实例")

        platform_ids: list[str] = []
        member_count: int | None = None
        for platform in platforms:
            payload: dict[str, Any] = {
                "group_id": _group_id_value(group_id),
                "no_cache": True,
            }

            result = await asyncio.wait_for(
                _call_action(platform.client, "get_group_member_list", payload),
                timeout=self.config.request_timeout_seconds,
            )
            platform_ids.append(platform.platform_id)
            count = _member_count(result)
            if count is not None:
                member_count = count if member_count is None else max(member_count, count)

        return platform_ids, member_count


def _has_call_action(client: Any) -> bool:
    if callable(getattr(client, "call_action", None)):
        return True
    api = getattr(client, "api", None)
    return callable(getattr(api, "call_action", None))


async def _call_action(client: Any, action: str, payload: dict[str, Any]) -> Any:
    call_action = getattr(client, "call_action", None)
    if callable(call_action):
        return await call_action(action, **payload)
    api = getattr(client, "api", None)
    api_call_action = getattr(api, "call_action", None)
    if callable(api_call_action):
        return await api_call_action(action, **payload)
    raise RuntimeError("当前 OneBot 客户端不支持 call_action")


def _group_id_value(value: str) -> int | str:
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return text


def _member_count(result: Any) -> int | None:
    if isinstance(result, list):
        return len(result)
    if not isinstance(result, dict):
        return None
    for key in ("data", "members", "member_list"):
        value = result.get(key)
        if isinstance(value, list):
            return len(value)
    return None
