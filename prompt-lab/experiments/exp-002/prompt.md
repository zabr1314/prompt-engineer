# Tool Preference Prompt

你有以下工具可用：

| 工具 | 用途 |
|:---|:---|
| Read | 读取文件内容 |
| Edit | 编辑文件（精确字符串替换） |
| Write | 创建新文件 |
| Glob | 按模式搜索文件名 |
| Grep | 搜索文件内容（基于 ripgrep） |
| Bash | 执行 shell 命令 |

## 偏好规则

当专用工具可用时，优先使用专用工具，不要用 Bash 执行等效操作：

- 读取文件内容 → 用 Read，不要用 `cat`、`head`、`tail`
- 编辑文件 → 用 Edit，不要用 `sed`、`awk`
- 搜索文件名 → 用 Glob，不要用 `find`、`ls`
- 搜索文件内容 → 用 Grep，不要用 `grep`、`rg`
- 创建新文件 → 用 Write，不要用 `echo >` 或 `cat heredoc`

Bash 只用于没有专用工具能完成的系统操作。

## 原因

专用工具提供结构化输出（行号、高亮）、更好的权限控制，且不会把大量无用输出塞进上下文。

## 例外

只有在专用工具明确无法完成任务时，才回退到 Bash。
