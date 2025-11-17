## 1. Implementation
- [ ] 1.1 扩展 Shell 任务状态存储，记录每个任务进入 RUNNING 的时间戳、最近活跃时间以及完成时间，
      驱动一个 `rich.live.Live` 状态条，每秒刷新 spinner、elapsed time 与 `esc` 提示，布局对齐 Codex CLI 顶部横幅。
- [ ] 1.2 基于 `console.color_system`/`COLOR_SYSTEM` 检测终端能力：TrueColor 使用 #53b3ff→#c56bff 渐变，
      Standard/EightBit 回退到 `bold cyan`→`magenta` 双色，`TERM=dumb` 或 `NO_COLOR` 时自动退化为单色文本。
- [ ] 1.3 将心跳条封装为独立 Live 区域，与 `console.print` 日志输出相互隔离，必要时使用 `Live.refresh()`/`console.capture()`
      协调，保证 `/tasks` 或普通输出不会把横幅挤出。
- [ ] 1.4 设计 Codex 风格的多任务列表：按“最后活跃时间”排序，仅显示最近 N 个（默认 4，可通过
      `shell.task_banner.visible_slots` 配置且数值需 ≥1，非法值自动回退到默认）并在底部提示
      `+k more (use /tasks)`；每行自带 spinner、耗时、快捷操作提示与任务徽标色。
- [ ] 1.5 为每行提供独立的渐变偏移或彩色徽标（按任务 ID hash），即使在降级配色中也能区分不同任务；
      hash 基于 task.id 并在完成/淡出期间保持稳定；`/tasks watch` 共享 Live 容器但不拦截键盘输入。
- [ ] 1.6 定义任务完成/失败后的过渡：行变为灰阶 `Done/Failed in …` 文案并停留 3 秒，若槽位不足或用户执行
      `/tasks clear`（若实现）则立即淡出；淡出动画互不干扰。
- [ ] 1.7 完成单色/ASCII 模式：当 `NO_COLOR`、`TERM=dumb` 等条件触发时，使用静态 ASCII spinner 与纯文本
      前缀替代颜色提示。
- [ ] 1.8 记录刷新频率（默认 1s，可配置）以及降级策略；确保 `/tasks watch` 等视图可与心跳条堆叠。
- [ ] 1.9 更新 shell-interaction 规范与回归测试，覆盖“静默任务心跳”“渐变/降级配色”“多任务排序裁剪”“watch 交互”“单色模式”场景。

## 2. Validation
- [ ] 2.1 添加/更新 pytest（或 TUI 快照测试）验证任务在无日志情况下仍持续渲染状态条，
      覆盖 TrueColor、EightBit、单色模式以及不同 `visible_slots` 配置。
- [ ] 2.2 手动在支持 TrueColor、EightBit、`NO_COLOR`/`TERM=dumb` 终端各运行一次 Shell，
      确认实时刷新、排序裁剪与 `+k more`、`/tasks watch` 快捷键协同正常。
