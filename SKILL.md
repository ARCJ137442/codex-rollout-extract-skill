---
name: codex-rollout-extract
description: |
  Use when a user provides chat/log/context files from another Agent session
  (e.g., Codex, a different Claude Code instance, Cursor, Windsurf) and needs
  to understand and continue that work. Also triggered by phrases like
  "恢复上下文", "接手工作", "之前做到哪了", "从聊天记录恢复",
  "交接", "handoff".
  NOT when the session is from Claude Code (use claude-code-session-extract instead).
  NOT when the current conversation already has sufficient context
  (use the regular conversation flow instead).
---

# Codex Rollout Extract

## 概述

**核心能力**：读取其他 Agent（Codex / Claude Code / Cursor 等）的聊天记录，自动提取已完成的工作、当前状态、下一步计划，输出结构化的交接报告（CONTEXT.md），让接手的 Agent 可以快速回到工作状态。

## 触发方式

| 场景 | 触发词 |
|------|--------|
| 读取聊天文件恢复 | "帮我恢复这个聊天记录"、"接手这个工作" |
| 交接场景 | "这是前面 Agent 留下的上下文" |
| 对话中断后 | "之前做到哪了"、"从这继续" |
| 有上下文文件 | 用户直接提供聊天记录文件路径或 session ID |

## 工作流程

```
① 定位文件 → ② 单次提取 → ③ 核对仓库状态 → ④ 验证代码 → ⑤ 合成报告
```

---

## 跨平台注意事项

> 本 skill 需要在 Windows / macOS / Linux 上均可运行。以下是已知的兼容性问题：

| 问题 | 解决方案 |
|------|----------|
| Python 可执行名不同 | Windows 上是 `python`，macOS/Linux 上是 `python3`。**优先使用 `python`，失败后回退 `python3`** |
| 路径格式差异 | Python 脚本内部统一用 `os.path.expanduser()` 处理 `~`，用 `os.path.join()` 拼路径。**不要在 Python 中硬编码 `/c/Users/` 或 `~`** |
| Bash 路径 vs Python 路径 | Git Bash (MSYS2) 用 `/c/Users/...`，Python 用 `C:/Users/...`。**传给 Python 的路径用 Windows 原生格式** |
| 编码 | 文件读写统一 `encoding='utf-8'` |
| glob 递归 | `glob.glob(pattern, recursive=True)` 在所有平台上均可用 |

---

## 步骤说明

### ① 定位文件

用户可能提供以下任一输入：
- **完整文件路径**（如 `~/.codex/sessions/2026/06/03/rollout-xxx.jsonl`）
- **Session ID**（如 `019e8b39-0a69-7991-82ae-9fa57a178916`）
- **聊天记录文件路径**（如 `.md`、`.json` 等非 JSONL 格式）

#### Codex JSONL 文件位置

Codex 会话日志通常位于以下目录：
- **活跃会话**: `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`
- **归档会话**: `~/.codex/archived_sessions/rollout-*.jsonl`

#### 如果用户给了 Session ID

直接用脚本的 `--session` 模式自动定位：

```bash
python scripts/codex_quick_scan.py --session 019e8b39-0a69-7991-82ae-9fa57a178916
```

> 脚本会自动在 `sessions/` 和 `archived_sessions/` 中搜索匹配文件。

#### 如果用户给了文件路径

直接传给脚本：

```bash
python scripts/codex_quick_scan.py /path/to/rollout-xxx.jsonl
```

#### 如果用户给的不是 JSONL

走「格式 B：非结构化」流程（见下文 ②-B）。

#### 快速判断格式

先读文件的前几行/前几 KB：

| 特征 | 格式 |
|------|------|
| 每行一个 JSON 对象，含 `"type": "session_meta"` | **Codex JSONL** → 走格式 A |
| 以 `[` 或 `{` 开头，含 `"messages"` 数组 | **Claude Code JSON** → 类似处理 |
| 包含 `<summary>` 或 `# 上下文恢复报告` | 已处理过的交接文档 → 直接读取 |
| 包含 `## 用户`、`## Assistant` | 手动整理的 Markdown → 走格式 B |

---

### ② 单次提取

#### 格式 A：Codex JSONL（推荐使用脚本）

**核心原则：一次遍历，全量提取。** 73MB 文件在 Python 流式读取下 <1s 完成。

##### 方法 1：使用脚本（推荐）

```bash
# 完整提取（默认模式）
python scripts/codex_quick_scan.py --session <session-id>

# 或直接指定文件
python scripts/codex_quick_scan.py <rollout-xxx.jsonl>

# 只提取 task_complete（快速交接）
python scripts/codex_quick_scan.py --task-complete <rollout-xxx.jsonl>
```

脚本输出包含以下所有 section：
- **SESSION META** — 仓库路径、分支、commit SHA、repo URL
- **EVENT TYPE DISTRIBUTION** — 事件类型统计
- **USER MESSAGES** — 用户输入（前 5 条预览）
- **TASK COMPLETES** — Agent 自生成的结构化工作总结（**最大价值点**）
- **LAST AGENT MESSAGE** — 最后一条 Agent 输出
- **TURN CONTEXTS** — 模型切换/上下文截断记录
- **DECISION HINT** — 自动判断是否需要深入提取

##### 脚本输出示例

```
============================================================
SESSION META
  CWD:      /path/to/your/project
  Branch:   main
  Commit:   795716535799c9225080cf84d899212ffdac2013
  Repo:     https://github.com/owner/repo
  Model:    custom
  Started:  2026-06-03T02:03:51.788Z

============================================================
EVENT TYPE DISTRIBUTION
  event_msg: 561
  response_item: 519
  replay_state: 142
  turn_context: 8
  session_meta: 1
  compacted: 1

============================================================
DECISION HINT
  task_complete 有内容 → 通常可以直接合成报告，无需深入 replay_state/response_item
```

##### 方法 2：手动提取（备选）

如果脚本不可用，可以手动运行 Python 片段。**注意：以下示例仅作为备选方案，优先使用脚本。**

**A2-1: 读 session_meta（第 1 行）**

```python
import json
meta = json.loads(open(filepath, 'r', encoding='utf-8').readline())
p = meta['payload']
print(f"CWD: {p.get('cwd')}")
print(f"Branch: {p.get('git', {}).get('branch')}")
print(f"Commit: {p.get('git', {}).get('commit_hash')}")
```

**A2-2: 扫描 task_complete（核心价值点）**

```python
with open(filepath, 'r', encoding='utf-8') as f:
    for line in f:
        obj = json.loads(line)
        if obj.get('type') == 'event_msg' and obj['payload'].get('type') == 'task_complete':
            msg = obj['payload'].get('last_agent_message', '')
            if msg.strip():  # 过滤空值
                print(msg)
                print('---DIVIDER---')
```

**A2-3: 扫描 user_message**

```python
with open(filepath, 'r', encoding='utf-8') as f:
    for line in f:
        obj = json.loads(line)
        if obj.get('type') == 'event_msg':
            p = obj['payload']
            if p.get('type') == 'user_message':
                msg = p.get('message', '')
                if msg.strip():  # 过滤空值
                    print(msg.strip()[:500])
```

##### 提取决策树

```
脚本输出后，根据 DECISION HINT 决定是否深入：

┌─ task_complete 有内容？
│   ├─ YES → 通常可以直接合成报告。
│   │        只有当 task_complete 明显不完整时才深入。
│   └─ NO
│       ├─ 有 agent_message？
│       │   ├─ YES → 从 agent_msgs + user_msgs 重建工作流
│       │   └─ NO → 需要深入 replay_state / response_item
│       └─ 有 turn_aborted？
│           └─ YES → 注意：任务被中断，可能没有完成
│
└─ 需要深入时（罕见）：
    - replay_state：提取每个 turn 的 prompt_input（含用户消息和工具结果）
    - response_item：提取工具调用记录（Bash/Read/Write 等）
    - 这两个信息量大，只在 task_complete 缺失时使用
```

##### Codex JSONL 结构参考

| 类型 | 数量级 | 用途 |
|------|--------|------|
| `session_meta` | 1 | **必读** — 会话元信息 |
| `event_msg` | ~500-2500 | 事件流（**主要提取源**） |
| `response_item` | ~500-2500 | 原始对话消息（信息量大，按需提取） |
| `replay_state` | ~100-750 | 重放状态（含 prompt_input，按需提取） |
| `turn_context` | ~5-25 | Turn 切换上下文（模型、截断策略） |
| `compacted` | ~1-10 | 上下文压缩摘要 |

---

#### 格式 B：普通 Markdown / 文本聊天记录（非结构化）

搜索以下关键词片段（大小写不敏感）：

| 关键词 | 提取目标 |
|--------|----------|
| `git log`、`git status`、`git diff` | 仓库状态信息 |
| `cargo check`、`cargo build`、`npm run`、`yarn build` | 编译/构建状态 |
| `Read`、`读取`、`查看文件` | 读取了哪些文件 |
| `Write`、`Edit`、`创建`、`修改` | 改动了哪些文件 |
| `TODO`、`下一步`、`计划`、`待做` | 未完成的工作 |
| `报错`、`错误`、`error`、`failed` | 已知问题 |
| `分支:`、`branch:`、`feat/` | 当前工作分支 |
| `提交`、`commit`、`SHA` | 已完成的提交 |

---

#### 通用提取清单（两种格式都适用）

| 提取项 | 关注什么 |
|--------|----------|
| **任务目标** | 这次工作的核心目标是什么 |
| **已完成的任务** | 哪些工作已经完成并提交了 |
| **当前工作** | 还有哪些未提交的修改 |
| **涉及的文件** | 改动了哪些文件（提取文件路径） |
| **编译/测试状态** | 构建和测试结果 |
| **下一步计划** | 计划做什么、还有什么待做 |
| **已知问题** | 报错、TODO、遗留问题 |

### ③ 核对仓库状态

读取完记录后，**必须**逐条验证记录中提到的信息与仓库实际情况是否一致：

```bash
# 基础信息（必做）
git log --oneline -10      # 看最近提交，确认分支和进度
git status --short          # 看工作树状态
git branch                  # 确认当前分支

# 看具体修改（如果有改动）
git diff --stat             # 概览
git diff                    # 细节
```

**验证要点**：
- 聊天记录里提到的提交 SHA 是否存在？→ `git log --oneline | grep <sha>`
- 聊天记录里提到的修改文件是否还在工作树？→ 对比 `git status`

### ④ 验证代码状态

根据项目类型运行编译/测试验证：

```bash
# Rust 项目
cargo check 2>&1 | tail -20

# Node/TS 项目
npm run build 2>&1 | tail -20

# 测试（可选，视聊天记录中是否有测试而定）
```

**如果聊天记录中的报错信息在验证中复现了，在报告中特别标注**。

### ⑤ 合成交接报告（CONTEXT.md）

输出格式如下：

```markdown
# 上下文恢复报告

## 来源信息
- 原始 Agent 类型: [Codex / Claude Code / 其他]
- 聊天记录文件: [文件路径]
- 仓库路径: [绝对路径]
- 当前分支: [git branch 结果]
- 最新提交: [git log -1 结果]
- 报告生成时间: [时间戳]

## 已完成的工作

列出已提交的成果，引用具体提交 SHA。

| 提交 | 内容 | 文件 |
|------|------|------|
| `xxxxxx` | 功能描述 | paths |

## 当前工作树状态

列出未提交的修改，描述每处改动的意图。

| 文件 | 改动内容 | 完成度 |
|------|----------|--------|
| `path/to/file.rs` | 新增了 XXX 功能 | 完成 / 进行中 |

## 验证结果

| 检查项 | 状态 | 备注 |
|--------|------|------|
| git log 一致性 | Y/N | |
| 工作树匹配 | Y/N | |
| 编译检查 | Y/N | |
| 测试 | Y/N / skip | |

## 已知问题

1. 问题描述（带文件路径和行号）

## 下一步计划

1. 按优先级排列的 TODO
```

## 输出处理

合成报告后，向用户确认：

1. **上下文确认**："这是我从聊天记录中恢复的上下文，你看是否符合预期？"
2. **写入选项**："要不要我把这份报告写入到项目中的推荐位置？"（如 `CONTEXT.md` 或 `docs/handoff/`）
3. **继续工作**："确认后我直接继续下一步工作"

## 核心原则

1. **先验证，再报告** — 聊天记录可能过时，必须用 git / build 等命令核对当前状态
2. **不加幻觉** — 聊天记录里没有的信息不要编造，明确标注"记录中未提及"
3. **保留原始上下文** — 如果聊天记录中的关键信息在验证中复现，保留并在报告中标记
4. **结构优先** — 表格化的报告比大段描述更容易被新 Agent 读取
5. **不破坏已有工作** — 只读取不写入，等用户确认后再继续
6. **单次遍历** — 大文件（100MB+）也只读一遍，流式处理
7. **空值过滤** — 所有提取都加 `if msg.strip()` 避免返回空块浪费上下文
