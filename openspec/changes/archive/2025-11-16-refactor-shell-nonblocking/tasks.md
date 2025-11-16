## 1. 架构与基础设施
- [x] 1.1 梳理现有 Shell UI 输入->执行流程，列出所有阻塞点。
- [x] 1.2 设计命令队列、执行 worker、状态存储与 wire 订阅之间的接口定义。
- [x] 1.3 在 openspec/specs 中补充 `shell-interaction` 能力的正式规范并通过校验。

## 2. 实现命令调度
- [x] 2.1 在 `ui/shell` 新增 `CommandQueue`、`Executor`、`StateStore` 等模块，完成最小工作流。
- [x] 2.2 使 prompt-toolkit 输入线程仅负责入队命令，立即刷新提示符。
- [x] 2.3 Worker 异步执行 soul，支持同时跟踪多个任务状态。

## 3. 状态与事件处理
- [x] 3.1 扩展 wire 事件载体以附带任务 ID，UI 根据事件更新 Store。
- [x] 3.2 支持 `/status` `/cancel <id>` 等元命令，提供任务管理能力。
- [x] 3.3 将审批请求与工具输出流式写入 Store，UI 实时展示。

## 4. 测试与文档
- [ ] 4.1 为新调度器添加单元/集成测试，确保多任务、取消、审批路径工作。
- [x] 4.2 更新 `docs/architecture.md` 与 README 中的 Shell 章节，描述异步模型与操作方式。
- [x] 4.3 验证 `openspec validate refactor-shell-nonblocking --strict` 通过，并记录迁移注意事项。
