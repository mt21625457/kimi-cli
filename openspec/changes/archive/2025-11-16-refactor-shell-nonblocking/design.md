# 方案概述
Shell UI 需要保持持续可输入，因此将“输入采集”与“KimiSoul 执行”解耦，采用事件驱动架构：

1. **CommandQueue**：所有用户指令都被包装为 `UserCommand`（含序列号、payload、元命令标记）并入队。
2. **Dispatcher**：单独协程监听队列，创建任务 ID、更新状态存储，并把指令交给执行器。
3. **Executor**：后台 worker，内部维护 `task_id -> asyncio.Task` 映射，负责调用 `KimiSoul.run()`；执行过程中通过扩展的 Wire 事件将 Step/Approval 输出给 UI。
4. **StateStore**：集中保存任务状态、实时日志、审批对话框信息，暴露订阅接口供渲染层刷新。
5. **Renderer**：根据 StateStore 进行多窗口渲染（提示行、任务面板、日志面板等），不再被 `run()` 阻塞。

# 组件关系
```
Prompt/Input -> CommandQueue -> Dispatcher -> Executor -> KimiSoul
                                       |             |
                                   StateStore <----- WireSubscriber
                                       |
                                   Renderer/UI
```

# 关键接口
- `UserCommand`: `{ task_id, raw_text, created_at, type }`
- `TaskState`: `enum { queued, running, waiting_approval, cancelling, succeeded, failed }`
- `StateStore` 发布 `async def watch()` 供 UI 获取增量更新。
- `Wire` 事件添加 `task_id` 字段，Task 工具或子代理转发事件时保留该字段。

# 任务并发策略
- MVP 维持单 worker，保证顺序执行但 UI 不阻塞。
- `Executor` 需要以接口形式 (`ICommandExecutor`) 暴露 `dispatch(command)`，后续可以注入 N 个 worker 的实现。
- 当启用多 worker 时，每个 worker 应持有独立的 `KimiSoul`/`Context`，防止共享实例导致工具状态、审批队列互串；设计上预留 `ExecutorFactory` 勾子用于创建隔离的 runtime。

# 取消机制
- `/cancel <id>` -> `Dispatcher` 设置 TaskState=cancel_requested，向对应 asyncio.Task 发 `cancel()`；Soul 捕捉 `CancelledError` 后写入结束事件。
- 工具层若正在等待审批，则 UI 可直接拒绝审批并提示“任务已取消”。

# 兼容性
- Print/ACP/Wire 模式保持原有同步行为；仅 Shell UI 引入该调度器。
- 现有历史文件/Session 逻辑不变，任务 ID 只在 UI 层使用。

# 风险与缓解
| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| Wire 事件缺少 task ID | UI 无法区分任务日志 | 在命令入队时生成 ID，并通过 `wire_context.task_id` 注入到 `KimiSoul.run()`；工具事件读取该字段并原样透传 |
| 审批/子代理误路由 | 可能阻塞或丢失请求 | Task 工具在派发子代理事件时附带父 task ID；UI 根据 ID 决定显示位置 |
| 多任务共享 KimiSoul 造成状态污染 | 结果互串 | MVP 采用串行队列 + 单实例；当配置多 worker 时，通过 `ExecutorFactory` 为每个 worker 创建独立 `KimiSoul` |
| 取消语义复杂 | 可能遗留僵尸任务 | 统一使用 asyncio cancellation，并在 StateStore 中设置超时兜底，必要时强制标记失败 |
