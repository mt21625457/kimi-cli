## ADDED Requirements

### Requirement: Shell UI SHALL 支持非阻塞指令输入
Shell 模式在处理任何指令时 SHALL 保持提示符可用、允许用户继续输入或管理后台任务，并提供任务级状态可见性。

#### Scenario: 长任务执行期间继续输入
- **Given** 用户在 Shell 模式下输入需要数分钟的命令（例如 `make test`）
- **When** 命令被派发给 KimiSoul 执行
- **Then** 提示符应立即回到可输入状态，并允许用户输入新的指令或查看任务状态

#### Scenario: 并发任务状态可见
- **Given** 至少两个命令被先后提交
- **When** Shell UI 展示任务列表
- **Then** 每个任务都应显示唯一 ID、当前状态（排队/执行/等待审批/完成/失败/取消）以及最新几条输出

#### Scenario: 用户取消指定任务
- **Given** 某个任务仍在执行或等待审批
- **When** 用户输入 `/cancel <taskId>`
- **Then** Shell UI 应请求终止该任务的执行（向后台 worker 发送取消信号），并在任务列表中标记为“已取消”或者“取消失败”

#### Scenario: 审批请求不阻塞输入
- **Given** 后台任务调用需要审批的工具
- **When** Approval 请求弹出
- **Then** UI 应显示可交互的审批面板，同时保持主提示符可继续输入其他命令
