#!/usr/bin/env python
# GitHub OpenClaw Radar - v0.1
# 掃描 GitHub 上與 OpenClaw 相關的最新動態，輸出 JSON + 簡易文字報告。

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUTPUT_PATH = Path("github_openclaw_radar.json")

GH_BIN = "/home/linuxbrew/.linuxbrew/bin/gh"  # 依你目前環境安裝位置


def run_gh(args):
    """呼叫 gh CLI 並回傳 JSON 結果（list 或 dict）。"""
    cmd = [GH_BIN] + args
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out)


def iso_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def is_recent(ts: str, hours: int = 24) -> bool:
    try:
        dt = iso_to_dt(ts)
    except Exception:
        return False
    now = datetime.now(timezone.utc)
    return now - dt <= timedelta(hours=hours)


def fetch_core_issues(hours: int = 24):
    issues = run_gh([
        "issue",
        "list",
        "--repo",
        "openclaw/openclaw",
        "--state",
        "all",
        "--limit",
        "50",
        "--json",
        "number,title,state,createdAt,updatedAt,author,url",
    ])
    recent = []
    for it in issues:
        updated = it.get("updatedAt") or it.get("createdAt")
        if updated and is_recent(updated, hours=hours):
            recent.append(it)
    return recent


def fetch_core_prs(hours: int = 24):
    prs = run_gh([
        "pr",
        "list",
        "--repo",
        "openclaw/openclaw",
        "--state",
        "all",
        "--limit",
        "50",
        "--json",
        "number,title,state,createdAt,updatedAt,author,url,mergedAt",
    ])
    recent = []
    for it in prs:
        updated = it.get("updatedAt") or it.get("createdAt") or it.get("mergedAt")
        if updated and is_recent(updated, hours=hours):
            recent.append(it)
    return recent


def fetch_openclaw_repos(hours: int = 24):
    # 搜尋名字或描述中含 openclaw 的 repo
    repos = run_gh([
        "search",
        "repos",
        "openclaw",
        "--sort",
        "updated",
        "--order",
        "desc",
        "--limit",
        "30",
        "--json",
        "name,fullName,description,updatedAt,createdAt,url,owner",
    ])
    recent = []
    for r in repos:
        updated = r.get("updatedAt") or r.get("createdAt")
        if updated and is_recent(updated, hours=hours):
            recent.append(r)
    return recent


def build_snapshot(hours: int = 24):
    snapshot = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "windowHours": hours,
        "coreIssues": fetch_core_issues(hours=hours),
        "corePRs": fetch_core_prs(hours=hours),
        "repos": fetch_openclaw_repos(hours=hours),
    }
    return snapshot


def classify_pr(title: str) -> str:
    t = title.lower()
    # 簡單 heuristic：先看 conventional commit prefix，再看關鍵字
    if t.startswith("fix") or "bug" in t or "error" in t:
        return "bug"
    if t.startswith("feat") or "feature" in t or "add " in t:
        return "feature"
    if t.startswith("docs") or "doc" in t or "readme" in t:
        return "docs"
    if "refactor" in t:
        return "refactor"
    return "other"


def summarize(snapshot: dict) -> str:
    hours = snapshot.get("windowHours", 24)
    issues = snapshot.get("coreIssues", [])
    prs = snapshot.get("corePRs", [])
    repos = snapshot.get("repos", [])

    lines = []
    # 大標題
    lines.append(f"## GitHub OpenClaw Radar（最近 {hours} 小時）\n")

    # 摘要段
    issue_count = len(issues)
    pr_count = len(prs)
    repo_count = len(repos)
    lines.append("### 摘要")
    lines.append(f"- Issues 更新數量：約 {issue_count} 則")
    lines.append(f"- PR 更新數量：約 {pr_count} 則（已依 bug/feature/docs/other 分類）")
    lines.append(f"- 最近更新的 OpenClaw 相關 repo：約 {repo_count} 個")
    lines.append("")

    # Issues table
    lines.append("### [openclaw/openclaw] Issues（最近 {hours} 小時）")
    if not issues:
        lines.append("- 最近沒有新的或更新的 issue\n")
    else:
        lines.append("| # | 狀態 | 提出人 | 標題 |")
        lines.append("|---|------|--------|------|")
        for it in issues[:10]:
            num = it.get("number")
            title = (it.get("title") or "").strip().replace("|", "‖")
            state = it.get("state") or "?"
            author = (it.get("author") or {}).get("login") if isinstance(it.get("author"), dict) else None
            author = author or "?"
            url = it.get("url")
            lines.append(f"| {num} | {state} | {author} | [{title}]({url}) |")
        lines.append("")

    # PRs table with type classification
    lines.append("### [openclaw/openclaw] Pull Requests（分類：bug/feature/docs/other）")
    if not prs:
        lines.append("- 最近沒有新的或更新的 PR\n")
    else:
        lines.append("| # | 類型 | 狀態 | 作者 | 標題 |")
        lines.append("|---|------|------|------|------|")
        for it in prs[:10]:
            num = it.get("number")
            title = (it.get("title") or "").strip().replace("|", "‖")
            state = it.get("state") or "?"
            author = (it.get("author") or {}).get("login") if isinstance(it.get("author"), dict) else None
            author = author or "?"
            url = it.get("url")
            pr_type = classify_pr(title)
            lines.append(f"| {num} | {pr_type} | {state} | {author} | [{title}]({url}) |")
        lines.append("")

    # Repos table
    lines.append("### [GitHub] 最近更新的 OpenClaw 相關 repo")
    if not repos:
        lines.append("- 最近沒有新的或更新的相關 repo")
    else:
        lines.append("| Repo | 作者 | 說明 |")
        lines.append("|------|------|------|")
        for r in repos[:10]:
            full = (r.get("fullName") or r.get("name") or "").replace("|", "‖")
            desc = (r.get("description") or "").strip().replace("|", "‖")
            url = r.get("url")
            owner = (r.get("owner") or {}).get("login") if isinstance(r.get("owner"), dict) else None
            owner = owner or "?"
            if len(desc) > 80:
                desc = desc[:77] + "..."
            lines.append(f"| [{full}]({url}) | {owner} | {desc} |")

    return "\n".join(lines)


def main():
    snapshot = build_snapshot(hours=24)
    OUTPUT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    report = summarize(snapshot)
    print(report)


if __name__ == "__main__":
    main()
