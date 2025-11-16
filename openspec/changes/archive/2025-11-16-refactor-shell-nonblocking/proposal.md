## Why
Shell UI 当前在 `prompt` 收到指令后会阻塞 `KimiSoul.run()`，用户无法继续输入或管理任务，长时间执行（如运行测试、抓日志）时体验极差，也无法实现任务并行或取消。

## What Changes
- 引入命令队列 + 后台执行器，将输入采集与 soul 执行解耦，保证提示符始终可用。
- 在 UI 层增加任务状态管理、取消接口与实时事件订阅，以便展示多任务进度与审批请求。
- 扩展 wire/执行上下文，在 Step/Approval 事件中携带任务 ID，确保 UI 能正确路由反馈。
- 更新文档与测试，明确新的并发模型与用户交互流程。

## Impact
- Affected specs: shell-interaction
- Affected code: `src/kimi_cli/ui/shell/*`, `src/kimi_cli/wire/*`, `src/kimi_cli/soul/kimisoul.py`, 文档与相关测试。
