#!/usr/bin/env python3
"""
Codex JSONL 提取器 — 单次遍历，全量提取。

用法：
    # 1. 按文件路径直接扫描
    python codex_quick_scan.py <rollout-xxx.jsonl>

    2. 按 session ID 自动定位文件
    python codex_quick_scan.py --session <session-id> [--codex-home ~/.codex]

    3. 只输出 task_complete（用于快速交接）
    python codex_quick_scan.py --task-complete <rollout-xxx.jsonl>
"""
import json
import os
import sys
import glob


def find_rollout(session_id, codex_home=None):
    """给定 session ID，在 codex sessions 目录中搜索对应文件。"""
    if codex_home is None:
        codex_home = os.path.expanduser("~/.codex")

    # 主目录：sessions/YYYY/MM/DD/
    pattern = os.path.join(codex_home, "sessions", "**", "*.jsonl")
    for f in glob.glob(pattern, recursive=True):
        if session_id in os.path.basename(f):
            return f

    # 归档目录
    pattern = os.path.join(codex_home, "archived_sessions", "*.jsonl")
    for f in glob.glob(pattern):
        if session_id in os.path.basename(f):
            return f

    return None


def extract(filepath, mode="full"):
    """
    单次遍历 JSONL 文件，提取所有关键信息。
    mode: "full" | "task_complete"
    返回 dict。
    """
    result = {
        "meta": None,
        "task_completes": [],
        "user_msgs": [],
        "agent_msgs": [],
        "turn_contexts": [],
        "event_types": {},
        "turn_aborted": 0,
        "compacted_summaries": [],
    }

    with open(filepath, "r", encoding="utf-8") as f:
        # --- session_meta (第1行) ---
        first = json.loads(f.readline())
        result["event_types"][first.get("type", "unknown")] = 1

        if first.get("type") == "session_meta":
            p = first["payload"]
            result["meta"] = {
                "cwd": p.get("cwd", "N/A"),
                "branch": p.get("git", {}).get("branch", "N/A"),
                "commit": p.get("git", {}).get("commit_hash", "N/A"),
                "repo_url": p.get("git", {}).get("repository_url", "N/A"),
                "model": p.get("model_provider", "N/A"),
                "timestamp": p.get("timestamp", "N/A"),
            }

        # --- 单次遍历提取 ---
        for line in f:
            obj = json.loads(line)
            t = obj.get("type", "unknown")
            result["event_types"][t] = result["event_types"].get(t, 0) + 1

            if t == "event_msg":
                p = obj.get("payload", {})
                et = p.get("type", "")
                msg = p.get("message", "")

                if et == "user_message" and msg.strip():
                    result["user_msgs"].append(msg.strip())

                elif et == "agent_message" and msg.strip():
                    result["agent_msgs"].append(msg.strip())

                elif et == "task_complete":
                    last_msg = p.get("last_agent_message", "")
                    if last_msg and last_msg.strip():
                        result["task_completes"].append(last_msg.strip())

                elif et == "turn_aborted":
                    result["turn_aborted"] += 1

            elif t == "compacted":
                p = obj.get("payload", {})
                rh = p.get("replacement_history", "")
                if rh:
                    result["compacted_summaries"].append(
                        rh[:500] if isinstance(rh, str) else json.dumps(rh, ensure_ascii=False)[:500]
                    )

            elif t == "turn_context":
                p = obj.get("payload", {})
                summary = p.get("summary", "")
                model = p.get("model", "")
                if summary and summary.strip():
                    result["turn_contexts"].append({
                        "model": model,
                        "summary": summary.strip()[:300],
                    })

    return result


def print_full(result):
    """格式化输出完整提取结果。"""
    meta = result["meta"]

    # --- SESSION META ---
    print("=" * 60)
    print("SESSION META")
    if meta:
        print(f"  CWD:      {meta['cwd']}")
        print(f"  Branch:   {meta['branch']}")
        print(f"  Commit:   {meta['commit']}")
        print(f"  Repo:     {meta['repo_url']}")
        print(f"  Model:    {meta['model']}")
        print(f"  Started:  {meta['timestamp']}")
    else:
        print("  (no session_meta found)")
    print()

    # --- EVENT TYPE DISTRIBUTION ---
    print("=" * 60)
    print("EVENT TYPE DISTRIBUTION")
    for k, v in sorted(result["event_types"].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print()

    # --- USER MESSAGES ---
    if result["user_msgs"]:
        print("=" * 60)
        print(f"USER MESSAGES ({len(result['user_msgs'])} total, showing first 5)")
        for i, m in enumerate(result["user_msgs"][:5]):
            preview = m[:500]
            print(f"  [{i+1}] {preview}")
            print()

    # --- TASK COMPLETES (核心) ---
    if result["task_completes"]:
        print("=" * 60)
        print(f"TASK COMPLETES ({len(result['task_completes'])} total, showing all)")
        for i, tc in enumerate(result["task_completes"]):
            print(f"  --- TC[{i+1}] ---")
            print(tc)
            print()
    else:
        print("=" * 60)
        print("TASK COMPLETES: NONE")
        if result["turn_aborted"] > 0:
            print(f"  WARNING: {result['turn_aborted']} turns aborted, no task completed")
        print()

    # --- LAST AGENT MESSAGE ---
    if result["agent_msgs"]:
        print("=" * 60)
        print("LAST AGENT MESSAGE")
        print(result["agent_msgs"][-1][:2000])
        print()

    # --- TURN CONTEXTS (模型切换/截断) ---
    if result["turn_contexts"]:
        print("=" * 60)
        print(f"TURN CONTEXTS ({len(result['turn_contexts'])} total, showing last 3)")
        for tc in result["turn_contexts"][-3:]:
            print(f"  Model: {tc['model']}")
            print(f"  Summary: {tc['summary'][:200]}")
            print()

    # --- DECISION HINT ---
    print("=" * 60)
    print("DECISION HINT")
    if result["task_completes"]:
        print("  task_complete 有内容 → 通常可以直接合成报告，无需深入 replay_state/response_item")
    elif result["agent_msgs"]:
        print("  无 task_complete 但有 agent_message → 从 agent_msgs + user_msgs 重建工作流")
    else:
        print("  信息极少 → 需要深入 replay_state/response_item 提取")
    print()


def print_task_complete_only(result):
    """只输出 task_complete 内容（用于快速交接）。"""
    if result["task_completes"]:
        for i, tc in enumerate(result["task_completes"]):
            print(f"=== TC[{i+1}] ===")
            print(tc)
            print()
    else:
        print("(no task_complete events found)")


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  python codex_quick_scan.py <rollout-xxx.jsonl>")
        print("  python codex_quick_scan.py --session <session-id> [--codex-home <path>]")
        print("  python codex_quick_scan.py --task-complete <rollout-xxx.jsonl>")
        sys.exit(1)

    # 解析参数
    mode = "full"
    filepath = None
    codex_home = None

    i = 0
    while i < len(args):
        if args[i] == "--session" and i + 1 < len(args):
            session_id = args[i + 1]
            i += 2
            filepath = find_rollout(session_id, codex_home)
            if not filepath:
                print(f"ERROR: Cannot find rollout file for session {session_id}")
                sys.exit(1)
            print(f"Found: {filepath}")
            print()
        elif args[i] == "--codex-home" and i + 1 < len(args):
            codex_home = args[i + 1]
            i += 2
        elif args[i] == "--task-complete" and i + 1 < len(args):
            mode = "task_complete"
            filepath = args[i + 1]
            i += 2
        else:
            filepath = args[i]
            i += 1

    if not filepath:
        print("ERROR: No input file specified")
        sys.exit(1)

    # 检查文件存在
    if not os.path.isfile(filepath):
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    # 文件大小提示
    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    if size_mb > 100:
        print(f"NOTE: File is {size_mb:.1f}MB, streaming line-by-line (safe for any size)")
        print()

    # 提取
    result = extract(filepath, mode)

    # 输出
    if mode == "full":
        print_full(result)
    elif mode == "task_complete":
        print_task_complete_only(result)


if __name__ == "__main__":
    main()
