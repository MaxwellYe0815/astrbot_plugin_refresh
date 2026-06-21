# astrbot_plugin_refresh

一个QQ群成员资料定时刷新插件。支持设置重点刷新群聊、刷新间隔等。

适合用于aiocqhttp框架，解决群名片、昵称、角色等资料长期不更新的问题。

## 功能

- 重点群：按固定间隔刷新，默认每小时一次。
- 普通群：按队列分批刷新，默认每小时刷新一个。
- 手动刷新：可立即刷新当前群或指定群。
- 群名单管理：可直接用聊天命令添加、移除、调整群聊分组。
- 状态记录：记录最近刷新时间、成员数、失败原因和普通群队列游标。

插件只负责触发 OneBot API，不保存成员资料。成员信息缓存仍由OneBot框架自己维护。

## 快速开始
### 安装说明

1. 将插件文件夹 `astrbot_plugin_refresh` 放入 AstrBot 的 `data/plugins` 目录
2. 在 AstrBot WebUI 中启用插件
3. 根据需要配置插件参数


## 配置

群名单可以在 WebUI 中填写，也可以用聊天命令维护。

常用配置：

- `priority_groups`: 重点群号列表。
- `normal_groups`: 普通群号列表。
- `priority_interval_seconds`: 重点群刷新间隔，默认 `3600`。
- `normal_interval_seconds`: 普通群队列刷新间隔，默认 `3600`。
- `normal_groups_per_interval`: 每轮普通群刷新数量，默认 `1`。
- `jitter_seconds`: 重点群刷新错峰秒数，默认 `300`。
- `startup_delay_seconds`: 启动后延迟刷新秒数，默认 `60`。
- `request_timeout_seconds`: OneBot API 调用超时秒数，默认 `60`。

命令添加或删除群时，会写入 AstrBot 的插件配置文件。刷新状态会保存在插件数据目录的 `refresh_state.json` 中。

## 命令

| 命令 | 说明 |
| :--- | :--- |
| `/refresh status` | 查看运行状态 |
| `/refresh list` | 查看群名单 |
| `/refresh add [群号]` | 加入或设为普通群；群聊中可省略群号 |
| `/refresh add-priority [群号]` | 加入或设为重点群；群聊中可省略群号 |
| `/refresh remove [群号]` | 从刷新名单移除；群聊中可省略群号 |
| `/refresh now [群号]` | 立即刷新指定群；群聊中可省略群号 |


## 工作方式

- 每次刷新调用 `get_group_member_list(group_id, no_cache=true)`。
- SnowLuma / NapCatQQ 收到 API 请求后刷新自己的成员缓存。
- 后续其他插件和消息事件会读取到框架侧更新后的资料。
- 群名单保存在 AstrBot 插件配置中，刷新状态和普通群队列游标保存在插件数据目录中。

## 许可证

本项目遵循 AGPLv3 许可证。
