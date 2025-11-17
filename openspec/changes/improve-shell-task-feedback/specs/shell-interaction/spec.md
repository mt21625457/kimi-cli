## ADDED Requirements
### Requirement: Shell UI SHALL 提供实时任务心跳条
Shell UI SHALL 在任务进入 RUNNING 状态后自动在提示符区域上方渲染带有任务编号、
spinner、耗时与中断提示的“心跳”状态条，并至少每秒刷新一次，无需用户输入任何命令。

#### Scenario: 静默任务自动显示心跳
- **GIVEN** 用户启动了一个进入 RUNNING 状态但暂时没有产生输出的后台任务
- **WHEN** 任务开始执行后的 1 秒内
- **THEN** Shell UI 会显示形如 `[#{id}] Working (12s • esc to interrupt)` 的状态条，包含 spinner、
  逐秒递增的耗时、以及 `esc`/`ctrl+c` 的中断提示
- **AND** 状态条自动刷新，无需用户输入 `/tasks` 或其它命令

#### Scenario: 渐变色突显运行态
- **GIVEN** 终端报告 `console.color_system == "truecolor"`
- **WHEN** 心跳条被渲染
- **THEN** 文本需采用从 `#53b3ff` 向 `#c56bff` 左到右渐变的配色，spinner 使用渐变末端色，
  背景为 `#0f111a`，以区别于成功（绿色）或失败（红色）提示
- **AND** 渐变渲染必须遵循 Codex CLI 式“Working (…)" 横幅布局

#### Scenario: 受限终端的降级颜色
- **GIVEN** `console.color_system` 为 `standard` 或 `eight_bit`，或 TERM 指示不支持 TrueColor
- **WHEN** 心跳条需要显示
- **THEN** UI SHALL 回退为两段对比度 ≥ 4.5:1 的固定色（例如 `bold cyan` → `magenta`）并保持
  `[#{id}] Working …` 文案、spinner 与深色背景
- **AND** 降级路径仍需打印任务编号、耗时与 “esc to interrupt” 提示

#### Scenario: 横幅固定在提示符上方
- **GIVEN** Shell UI 处于交互输入状态
- **WHEN** 任务心跳条显示
- **THEN** 状态横幅 SHALL 固定在提示符上方、跨越可视宽度，并使用深色背景搭配渐变文字与 spinner，
  效果参考 Codex CLI `Working (12s • esc to interrupt)` 横幅
- **AND** 用户继续输入时横幅保持可见，只有在任务结束或被取消后才退出

#### Scenario: 多任务并行
- **GIVEN** 至少两个任务处于 RUNNING
- **WHEN** 心跳条在 Live 面板内呈现
- **THEN** 每个任务各占一行，按照“最后活跃时间”倒序排列，仅显示最近的 N 个（默认 4 个，可由
  `shell.task_banner.visible_slots` 配置），其余任务以 `+k more (use /tasks)` 提示表示
- **AND** 每行展示任务编号、spinner、耗时与中断提示，并根据任务 ID 计算轻微偏移的渐变或彩色徽标，
  即使终端宽度较窄也能区分不同任务，新任务加入时无需滚动历史日志即可看到

#### Scenario: 任务完成后自动收起
- **GIVEN** 当前任务的心跳条正在显示
- **WHEN** 任务完成或失败
- **THEN** 心跳条在 1 秒内替换为灰阶 “Done/Failed in {elapsed}s” 摘要行，停留 3 秒后淡出/移除，
  若新的活跃任务需要腾出槽位，则最旧的完成行立即淡出，同时 `/tasks clear`（若存在）会立即清空这些摘要
- **AND** 用户无需执行任何额外命令即可获知任务结果

#### Scenario: 心跳条与任务列表互补
- **GIVEN** 用户可通过 `/tasks` 或任务表格查看详细日志
- **WHEN** 心跳条显示
- **THEN** Shell UI SHALL 保留现有任务表格输出，心跳条仅提供额外实时提示，不会遮挡或替代 `/tasks`
- **AND** 任意 `console.print` 调用发生时，心跳横幅使用独立的 Live 区域保持稳定，避免闪烁或被挤出视图

#### Scenario: `/tasks watch` 友好
- **GIVEN** 用户执行 `/tasks watch` 或类似命令
- **WHEN** Live 面板需要在详细任务视图与心跳条之间共享空间
- **THEN** Shell UI SHALL 在同一 Live 容器中堆叠心跳条和 `/tasks watch` 表格，保持交互顺序与焦点一致
- **AND** 两个视图互不覆盖：心跳条固定在顶部表面，列表位于其下，退出 watch 后心跳条仍然可见
- **AND** 心跳条不拦截 watch 模式的键盘输入（滚动、退出、刷新等快捷键行为与无心跳条时一致）

#### Scenario: 无颜色/单色环境
- **GIVEN** `NO_COLOR`、`TERM=dumb` 或其他设置禁止彩色/动画输出
- **WHEN** 心跳条需要显示
- **THEN** UI SHALL 自动回退为单色文本行（静态 ASCII spinner、清晰的任务编号与耗时），同时保留
  排序、`+k more` 提示与 `/tasks watch` 兼容策略
