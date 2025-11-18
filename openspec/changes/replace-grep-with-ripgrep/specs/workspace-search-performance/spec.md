## ADDED Requirements
### Requirement: Grep commands SHALL be rewritten to ripgrep when safe
当 `cli_output.replace_grep_with_rg` 开关开启时，Kimi CLI MUST 拦截 Bash 工具中出现的 `grep`/`egrep`/`fgrep` 命令，并在可确定的情况下改写为 ripgrep（`rg`），以获得更快的搜索体验；当该开关关闭或语义无法保证一致时，CLI MUST 回退到原命令并提示用户。

#### Scenario: Auto rewrite simple grep
- **Given** 用户在 Shell 模式里输入 `cat foo.py | grep -n TODO`
- **When** Bash 工具开始执行该命令且 `cli_output.replace_grep_with_rg` 为 true
- **Then** CLI MUST 识别 `grep -n TODO` 并改写为等价的 `rg --line-number TODO`
- **AND** 改写结果 MUST 仅替换 grep 片段而保持其他管道步骤不变，使得 grep 的等价部分由 ripgrep 执行
- **AND** 命令转录头部 MUST 标记 `• Ran cat foo.py | rg --line-number TODO (auto-rewritten)` 并紧接一行 `│ original: cat foo.py | grep -n TODO` 以便用户审计

#### Scenario: Common options coverage
- **Given** 用户输入 `grep -R -n -i -e TODO --include '*.py' src`
- **When** CLI 对命令进行解析
- **Then** 自动改写 MUST 支持并映射 `-R/-r`, `-n`, `-i`, `-v`, `-w`, `-A/-B/-C`, `-e pattern`, `--include/--exclude`, 以及 `--color=never` 等常见选项
- **AND** 改写后的 ripgrep 命令 MUST 与原 grep 的语义一致（大小写、递归、输出控制等）
- **AND** 该行为 MUST 由自动化测试覆盖以确保后续回归。

#### Scenario: Unsupported grep falls back with warning
- **Given** 用户输入一个包含复杂 shell 逻辑（例如 here-doc 或 process substitution）的 `grep`
- **When** CLI 无法确定安全重写
- **Then** CLI MUST 保持原命令，并在转录或日志中提示“grep 未自动优化，请改用 Grep 工具或简化命令”。

#### Scenario: Non grep binaries stay untouched
- **Given** 用户运行 `git grep TODO` 或 `python mygrep.py`
- **When** CLI 解析命令并发现 `grep` 子串并非独立可执行（例如带有前缀 `git`)
- **Then** CLI MUST 不进行改写，并在日志中说明“检测到非 GNU grep 命令，未自动优化”，以避免行为偏差。

#### Scenario: Unsupported grep binary detection
- **Given** 用户通过 shell alias 或 PATH 指向 BusyBox/BSD 版 `grep`
- **When** CLI 解析到 `grep` 命令并解析实际可执行文件
- **Then** CLI MUST 在确认该二进制不属于受支持的 GNU grep 家族时跳过改写，并输出“检测到非受支持 grep 变体”提示，确保行为安全。

### Requirement: Ripgrep availability SHALL be ensured or guided
Kimi CLI MUST 在需要执行 ripgrep 时自动确保二进制可用（复用共享目录下载），若下载失败则输出明确的手动安装指引。

#### Scenario: Missing rg triggers auto install
- **Given** 用户首次运行 CLI，系统 PATH 中没有 `rg`
- **When** Bash/Grep 工具需要执行 ripgrep且用户已批准（或配置允许静默下载）
- **Then** CLI MUST 自动下载匹配平台的 rg 到共享 bin 目录，并在成功后继续执行命令而无需进一步干预。

#### Scenario: Download consent
- **Given** CLI 检测到系统缺少 `rg`
- **When** 即将触发自动下载
- **Then** CLI MUST 先取得用户的明确批准，或已在配置中启用了“无需确认的自动下载”，否则应中止下载并提示手动安装步骤。

#### Scenario: Source integrity verification
- **Given** CLI 从远端下载 rg
- **When** 归档文件下载完成
- **Then** CLI MUST 验证文件的哈希值或签名与预期一致，且下载源必须在配置中声明（例如官方 release 或可信 CDN），否则拒绝安装并提示用户手动获取。

#### Scenario: Download failure guidance
- **Given** 下载受到网络限制导致失败
- **When** CLI 无法取得 rg
- **Then** CLI MUST 返回错误并包含手动安装步骤或二进制 URL，确保用户理解如何解锁该功能。

### Requirement: User education and telemetry for search performance
CLI MUST 提供可配置的自动重写开关、向用户提示 ripgrep 语法、并记录无法重写的 `grep` 次数供调试。

#### Scenario: Configurable rewrite toggle
- **Given** 用户在 `~/.kimi/config.json` 中将 `cli_output.replace_grep_with_rg` 设为 false
- **When** CLI 解析 Bash 命令
- **Then** 任何 `grep` 命令 MUST 不被改写，同时 CLI 不得输出“auto-rewritten”标记。

#### Scenario: User guidance via tool descriptions
- **Given** 用户查看 Grep 工具描述或系统提示
- **When** CLI 呈现说明文案
- **Then** 文案 MUST 清晰指出“优先使用 ripgrep 语法/工具，Bash 中的 grep 会自动尝试优化”，以减少混淆。

#### Scenario: Transcript shows original command
- **Given** CLI 将 `grep` 改写为 `rg`
- **When** 命令执行完毕
- **Then** 转录 MUST 使用统一格式：命令头部展示改写后的命令并追加 `(auto-rewritten)`，紧跟一行 `│ original: <原始命令>`，footer 结束语中提示“可通过 cli_output.replace_grep_with_rg 配置关闭自动改写”。

#### Scenario: Telemetry counter
- **Given** CLI 遇到无法改写的 grep 命令
- **When** 命令执行完成
- **Then** CLI MUST 在日志或指标中记录该命令模式，供后续分析覆盖率。
