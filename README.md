# codex-rollout-extract

从 Codex JSONL rollout 文件中提取上下文，生成结构化交接报告，让接手的 Agent 快速恢复工作状态。

## 用途

当一个 Codex 会话中途挂掉、没有交接，留下几百 MB 的 JSONL 日志时，这个 skill 可以：

1. **读取 rollout JSONL** — 自动解析 `session_meta`、`event_msg`、`replay_state` 等事件类型
2. **提取关键信息** — 已完成的工作、当前代码状态、下一步计划、已知问题
3. **验证仓库一致性** — 用 `git log` / `git status` / `cargo check` 核对记录与实际情况
4. **输出交接报告** — 结构化的 `CONTEXT.md`，可被 Claude Code / Codex / 其他 Agent 直接读取

## 快速使用

```bash
# 1. 用快速扫描脚本预览 rollout 文件概览
python scripts/codex_quick_scan.py path/to/rollout-xxx.jsonl

# 2. 按 SKILL.md 指引逐步提取交接报告
```

详细工作流程见 [SKILL.md](SKILL.md)。

## 文件结构

```
├── SKILL.md                       # Skill 指令（含 Codex JSONL 解析策略）
├── README.md                      # 本文件
├── scripts/
│   └── codex_quick_scan.py        # Codex JSONL 快速扫描器
```

## 安装

作为 Claude Code skill 安装：

```bash
npx skills add ARCJ137442/codex-rollout-extract-skill
```

或直接克隆：

```bash
git clone https://github.com/ARCJ137442/codex-rollout-extract-skill.git
cp -r codex-rollout-extract-skill ~/.claude/skills/
```

## 许可证

MIT
