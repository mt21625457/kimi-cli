# Proposal: Improve Shell Task Feedback

## Change ID
improve-shell-task-feedback

## Summary
Elevate the Shell UI task feedback loop with Codex CLI–style running indicators that show task IDs,
elapsed time, and cancellation hints inside a color-gradient banner so users instantly know a
background job is alive even when it produces no logs, with first-class multi-task layout and
sorting that stay readable when many jobs run concurrently.

## Why
- 当前 Shell 任务在长时间静默时只有偶尔的状态输出，用户容易误以为任务卡死或忘记在运行。
- 缺少统一的视觉层级（颜色、spinner、提示文字），导致并发任务的信息噪声高、可读性差。
- 用户为了确认任务是否还活着需要输入额外命令（/tasks、/task watch），和“后台执行不打扰”的目标相悖。
- OpenAI Codex CLI 的交互示例（参见截图 `Working (12s • esc to interrupt)` 横幅）证明了顶部常驻渐变条、
  统一快捷键提示、紧凑表格化输出可以显著增强任务活跃感，是我们要对齐的体验基准。
- Codex CLI 还展示了 TrueColor/非 TrueColor 的兼容策略和“Live 区域 + 日志”互不干扰的做法，
  提醒我们在实现前就需要定义检测、降级与刷新策略。

- 扩展 Shell UI 的任务状态层，在任务进入 RUNNING 后立即显示与 Codex CLI `Working` 横幅一致的信息密度：
  `[#{id}] Working (elapsed • esc to interrupt)` 式样的渐变色提示条并每秒刷新，且默认固定在提示符上方。
- `Live` 面板按“最后活跃时间”倒序列出所有活跃条目。每行包含任务编号、spinner、耗时、快捷键提示，
  并用柔和的栅格分割（仿照 Codex CLI 的“状态条 + 列表”布局）；默认显示最近 4 个任务（可通过
  `~/.kimi/config.json.shell.task_banner.visible_slots` 配置），超出后显示 `+k more (use /tasks)` 提示，避免无限增长。
- 颜色方案采用从 #53b3ff 过渡到 #c56bff 的渐变，背景加深（如 #0f111a）模拟 Codex CLI 的夜间风格；
  每行的渐变起点会根据任务 ID 做轻微偏移，或在行首加入带 hash 色块的任务徽标，确保多任务在窄终端中仍可区分。
  若 `console.color_system` 非 TrueColor，则降级为 `bold cyan`→`magenta` 双色条（同样附带任务徽标），对比度 ≥ 4.5:1。
- Heartbeat 只做实时提醒，不取代 `/tasks` 或任务列表；完成/失败后每个任务的行会转为灰阶 `Done/Failed in …`
  摘要停留 3 秒，再淡出释放空间。如果期间有新任务加入、导致可视槽位不足，则最早的完成行会立即淡出；
  若环境中提供 `/tasks clear`（未来可选命令），心跳条应监听该事件并同步清空摘要。
- `/tasks watch` 与心跳条共享 Live 容器：心跳条固定在顶部且不拦截键盘输入、watch 模式的滚动/退出快捷键完全透明地穿透。
- 每秒刷新节奏默认 1s（可配置），以 Codex CLI 为基准提供“正在运行且可随时中断”的心跳感；性能优化留待后续迭代。

## Impact
- 大幅降低用户查询任务状态所需的交互成本，交互体验更“有生命力”。
- Shell 输出区域会有额外的实时刷新，需要确保 Live 面板与现有日志输出互不干扰，并评估 1s 刷新增量 CPU/IO。
- 真实地对齐 Codex CLI 的视觉基准，为后续扩展（例如多任务聚合视图、自动关注任务）奠定 UI/UX 基础。
- 需要引入终端能力检测和可访问性（对比度）策略，确保在各种终端中都具备可读性和一致的交互提示。

## Open Questions
1. 渐变色是否需要允许用户自定义主题？
2. 若终端不支持 TrueColor，是否需要降级方案（例如双色块或单色 spinner）？
