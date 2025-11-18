## 1. Implementation
- [ ] 1.1 添加 `cli_output.replace_grep_with_rg` 配置项并提供默认值（文档包含中英说明）
- [ ] 1.2 在 Bash 工具引入 `grep` → `rg` 重写模块（含日志、转录标记、原命令展示），覆盖常见 grep 选项并忽略非 GNU grep 可执行
- [ ] 1.3 对缺失 rg 的场景实现“检测→请求用户批准或读取静默配置→下载/安装→哈希校验→失败回退提示”的流程，并让 Bash/Grep 共享
- [ ] 1.4 更新 README/AGENTS 等文档（中英文）解释自动重写、配置开关、下载流程与手动安装指引
- [ ] 1.5 添加覆盖 rewriter 选项、非 GNU grep 检测、配置开关、下载审批/失败路径/哈希校验的测试
