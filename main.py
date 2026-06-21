from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from .core.config import PLUGIN_NAME
from .core.service import RefreshService


@register(PLUGIN_NAME, "飘寂叶", "定时刷新 OneBot 群成员资料缓存", "1.0.0")
class RefreshPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context, config)
        self.config = config if config is not None else {}
        self.service: RefreshService | None = None

    async def initialize(self):
        data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        self.service = RefreshService(
            self.context,
            data_dir=data_dir,
            runtime_config=self.config,
        )
        await self.service.start()
        logger.info(f"{PLUGIN_NAME} initialized at {data_dir}")

    async def terminate(self):
        if self.service is not None:
            await self.service.stop()
            self.service = None

    @filter.command_group("refresh")
    def refresh(self):
        pass

    @refresh.command("status")
    async def status(self, event: AstrMessageEvent):
        """查看 refresh 运行状态。"""
        yield event.plain_result(await self._service().status_text())

    @refresh.command("list")
    async def list_groups(self, event: AstrMessageEvent):
        """查看 refresh 群组配置。"""
        yield event.plain_result(await self._service().list_text())

    @refresh.command("add")
    async def add_group(self, event: AstrMessageEvent, group_id: str = ""):
        """把指定群或当前群设为普通群。"""
        if not self._can_manage(event):
            yield event.plain_result("只有管理员可以修改 refresh 群组名单。")
            return

        target_group_id = self._target_group_id(event, group_id)
        if not target_group_id:
            yield event.plain_result("请指定群号，或在群聊中使用 /refresh add。")
            return

        _, message = await self._service().add_group(target_group_id, priority=False)
        yield event.plain_result(message)

    @refresh.command("add-priority")
    async def add_priority_group(self, event: AstrMessageEvent, group_id: str = ""):
        """把指定群或当前群设为重点群。"""
        if not self._can_manage(event):
            yield event.plain_result("只有管理员可以修改 refresh 群组名单。")
            return

        target_group_id = self._target_group_id(event, group_id)
        if not target_group_id:
            yield event.plain_result(
                "请指定群号，或在群聊中使用 /refresh add-priority。"
            )
            return

        _, message = await self._service().add_group(target_group_id, priority=True)
        yield event.plain_result(message)

    @refresh.command("remove")
    async def remove_group(self, event: AstrMessageEvent, group_id: str = ""):
        """从刷新名单移除指定群或当前群。"""
        if not self._can_manage(event):
            yield event.plain_result("只有管理员可以修改 refresh 群组名单。")
            return

        target_group_id = self._target_group_id(event, group_id)
        if not target_group_id:
            yield event.plain_result("请指定群号，或在群聊中使用 /refresh remove。")
            return

        _, message = await self._service().remove_group(target_group_id)
        yield event.plain_result(message)

    @refresh.command("now")
    async def refresh_now(self, event: AstrMessageEvent, group_id: str = ""):
        """立即刷新指定群，未指定时刷新当前群。"""
        if not self._can_manage(event):
            yield event.plain_result("只有管理员可以手动触发 refresh。")
            return

        target_group_id = self._target_group_id(event, group_id)
        if not target_group_id:
            yield event.plain_result("请指定群号，或在群聊中使用 /refresh now。")
            return

        result = await self._service().refresh_group(target_group_id)
        if result.ok:
            count_text = (
                f"，成员数 {result.member_count}"
                if result.member_count is not None
                else ""
            )
            yield event.plain_result(f"已刷新群 {target_group_id}{count_text}。")
        else:
            yield event.plain_result(f"刷新群 {target_group_id} 失败：{result.message}")

    @refresh.command("tick")
    async def tick(self, event: AstrMessageEvent):
        """立即执行一轮到期任务检查。"""
        if not self._can_manage(event):
            yield event.plain_result("只有管理员可以手动触发 refresh。")
            return

        results = await self._service().run_due_once()
        if not results:
            yield event.plain_result("当前没有到期的刷新任务。")
            return
        ok_count = sum(1 for item in results if item.ok)
        yield event.plain_result(f"本轮刷新 {len(results)} 个群，成功 {ok_count} 个。")

    def _service(self) -> RefreshService:
        if self.service is None:
            raise RuntimeError("refresh service is not initialized")
        return self.service

    def _can_manage(self, event: AstrMessageEvent) -> bool:
        return not event.get_group_id() or event.is_admin()

    def _target_group_id(self, event: AstrMessageEvent, group_id: str = "") -> str:
        return str(group_id or "").strip() or str(event.get_group_id() or "").strip()
