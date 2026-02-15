#!/usr/bin/env python
"""Create a Notion page under the given parent page, with today's GitHub Radar report.

Requires:
- NOTION_API_KEY in environment (already configured via OpenClaw onboarding)
"""

import os
import sys
from datetime import datetime, timezone

import requests

import github_openclaw_radar as radar

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2025-09-03"
# Notion 目標頁面改用環境變數注入，避免在公開程式碼中硬編 page_id
PARENT_PAGE_ENV_KEY = "NOTION_PARENT_PAGE_ID"


def main() -> None:
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        print("NOTION_API_KEY not set in environment", file=sys.stderr)
        sys.exit(1)

    # Build latest snapshot + report text
    snapshot = radar.build_snapshot(hours=24)
    report = radar.summarize(snapshot)

    today_str = datetime.now(timezone.utc).astimezone().date().isoformat()
    title_text = f"{today_str} GitHub Radar"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    # 解析 snapshot，建立 Notion 原生 blocks（示範：大標題 + 摘要 + Issues 表格）
    issues = snapshot.get("coreIssues", [])
    prs = snapshot.get("corePRs", [])
    repos = snapshot.get("repos", [])

    children = []

    # Heading 2: 大標題
    children.append(
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"GitHub OpenClaw Radar（最近 {snapshot.get('windowHours', 24)} 小時）"}}
                ]
            },
        }
    )

    # Heading 3: 摘要
    issue_count = len(issues)
    pr_count = len(prs)
    repo_count = len(repos)
    children.append(
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "摘要"}}]},
        }
    )
    # 摘要 bullet list
    summary_lines = [
        f"Issues 更新數量：約 {issue_count} 則",
        f"PR 更新數量：約 {pr_count} 則（已依 bug/feature/docs/other 分類）",
        f"最近更新的 OpenClaw 相關 repo：約 {repo_count} 個",
    ]
    for s in summary_lines:
        children.append(
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": s}}]
                },
            }
        )

    # Heading 3: Issues 區塊
    children.append(
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [
                    {"type": "text", "text": {"content": "openclaw/openclaw Issues"}}
                ]
            },
        }
    )

    # Issues Table block（Notion 原生表格）
    # 4 欄：#, 狀態, 提出人, 標題
    issue_rows = []
    header_row = ["#", "狀態", "提出人", "標題"]
    issue_rows.append(header_row)

    for it in issues[:10]:
        num = str(it.get("number"))
        state = it.get("state") or "?"
        author = (it.get("author") or {}).get("login") if isinstance(it.get("author"), dict) else None
        author = author or "?"
        title = (it.get("title") or "").strip()
        url = it.get("url")
        title_content = title
        if url:
            title_cell = {
                "type": "text",
                "text": {"content": title_content, "link": {"url": url}},
            }
        else:
            title_cell = {"type": "text", "text": {"content": title_content}}

        row_cells = [
            {"type": "text", "text": {"content": num}},
            {"type": "text", "text": {"content": state}},
            {"type": "text", "text": {"content": author}},
            title_cell,
        ]
        issue_rows.append(row_cells)

    def make_table_block(rows, width):
        block = {
            "object": "block",
            "type": "table",
            "table": {
                "table_width": width,
                "has_column_header": True,
                "has_row_header": False,
                "children": [],
            },
        }
        for row in rows:
            cells = []
            for cell in row:
                if isinstance(cell, str):
                    rich_text = [{"type": "text", "text": {"content": cell}}]
                else:
                    rich_text = [cell]
                cells.append(rich_text)
            block["table"]["children"].append(
                {"object": "block", "type": "table_row", "table_row": {"cells": cells}}
            )
        return block

    children.append(make_table_block(issue_rows, width=4))

    # Heading 3: PRs 區塊
    children.append(
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [
                    {"type": "text", "text": {"content": "openclaw/openclaw Pull Requests"}}
                ]
            },
        }
    )

    # PRs Table block：5 欄：#, 類型, 狀態, 作者, 標題
    def classify_pr(title: str) -> str:
        t = title.lower()
        if t.startswith("fix") or "bug" in t or "error" in t:
            return "bug"
        if t.startswith("feat") or "feature" in t or "add " in t:
            return "feature"
        if t.startswith("docs") or "doc" in t or "readme" in t:
            return "docs"
        if "refactor" in t:
            return "refactor"
        return "other"

    pr_rows = []
    pr_rows.append(["#", "類型", "狀態", "作者", "標題"])
    for it in prs[:10]:
        num = str(it.get("number"))
        state = it.get("state") or "?"
        author = (it.get("author") or {}).get("login") if isinstance(it.get("author"), dict) else None
        author = author or "?"
        title = (it.get("title") or "").strip()
        url = it.get("url")
        pr_type = classify_pr(title)
        if url:
            title_cell = {
                "type": "text",
                "text": {"content": title, "link": {"url": url}},
            }
        else:
            title_cell = {"type": "text", "text": {"content": title}}
        pr_rows.append(
            [
                {"type": "text", "text": {"content": num}},
                {"type": "text", "text": {"content": pr_type}},
                {"type": "text", "text": {"content": state}},
                {"type": "text", "text": {"content": author}},
                title_cell,
            ]
        )

    children.append(make_table_block(pr_rows, width=5))

    # Heading 3: Repos 區塊
    children.append(
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [
                    {"type": "text", "text": {"content": "最近更新的 OpenClaw 相關 Repo"}}
                ]
            },
        }
    )

    # Repos Table：3 欄：Repo, 作者, 說明（英文）
    repo_rows = []
    repo_rows.append(["Repo", "作者", "說明"])
    for r in repos[:10]:
        full = (r.get("fullName") or r.get("name") or "").strip()
        owner = (r.get("owner") or {}).get("login") if isinstance(r.get("owner"), dict) else None
        owner = owner or "?"
        desc = (r.get("description") or "").strip()
        url = r.get("url")
        if len(desc) > 80:
            desc = desc[:77] + "..."
        if url:
            repo_cell = {
                "type": "text",
                "text": {"content": full, "link": {"url": url}},
            }
        else:
            repo_cell = {"type": "text", "text": {"content": full}}
        repo_rows.append(
            [
                repo_cell,
                {"type": "text", "text": {"content": owner}},
                {"type": "text", "text": {"content": desc}},
            ]
        )

    children.append(make_table_block(repo_rows, width=3))

    parent_page_id = os.environ.get(PARENT_PAGE_ENV_KEY)
    if not parent_page_id:
        print(f"{PARENT_PAGE_ENV_KEY} not set in environment", file=sys.stderr)
        sys.exit(1)

    payload = {
        "parent": {"page_id": parent_page_id},
        "properties": {
            "title": {
                "title": [
                    {"text": {"content": title_text}},
                ]
            }
        },
        "children": children,
    }

    resp = requests.post(NOTION_API_URL, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 400:
        print("Notion API error:", resp.status_code, resp.text, file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    page_id = data.get("id")
    print(f"Notion page created with id: {page_id}")


if __name__ == "__main__":
    main()
