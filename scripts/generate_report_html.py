#!/usr/bin/env python3
"""
将 reports/ 目录下的 Markdown 分析报告转换成 HTML 网页，
并维护一个累积的历史归档（reports-html/），生成首页索引 index.html。

用法:
    python deploy_to_amplify.py --market a-share
    python deploy_to_amplify.py --market us

环境变量:
    REPORT_GLOB        要查找的报告文件 glob 模式（默认 reports/*.md）
    SITE_DIR           历史网页累积目录（默认 reports-html）
"""

import argparse
import glob
import html
import os
import re
import sys
from datetime import datetime, timezone, timedelta


def find_latest_report(report_glob: str) -> str | None:
    """找到 reports/ 目录下最新生成的 Markdown 报告"""
    files = glob.glob(report_glob)
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def markdown_to_html_body(md_text: str) -> str:
    """
    极简 Markdown -> HTML 转换（不引入第三方依赖）。
    支持: # 标题, ## 标题, **加粗**, > 引用, 换行
    """
    lines = md_text.split("\n")
    html_lines = []
    for line in lines:
        line = line.rstrip()
        if line.startswith("### "):
            html_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("> "):
            html_lines.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        elif line.strip() == "":
            html_lines.append("<br>")
        else:
            # 处理行内 **加粗**
            escaped = html.escape(line)
            escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
            html_lines.append(f"<p>{escaped}</p>")
    return "\n".join(html_lines)


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", sans-serif;
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px 60px;
    line-height: 1.7;
    color: #1a1a1a;
    background: #f7f7f8;
  }}
  .card {{
    background: #fff;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }}
  h1 {{ font-size: 22px; margin-top: 0; }}
  h2 {{ font-size: 18px; color: #2563eb; margin-top: 28px; }}
  h3 {{ font-size: 16px; margin-top: 20px; }}
  p {{ margin: 8px 0; word-wrap: break-word; }}
  blockquote {{
    margin: 12px 0;
    padding: 8px 14px;
    background: #f0f4ff;
    border-left: 4px solid #2563eb;
    border-radius: 4px;
    color: #444;
  }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 16px; }}
  .back-link {{ display: inline-block; margin-top: 24px; color: #2563eb; text-decoration: none; }}
</style>
</head>
<body>
  <div class="card">
    <div class="meta">生成时间: {generated_at}</div>
    {body}
    <a class="back-link" href="index.html">← 返回历史报告列表</a>
  </div>
</body>
</html>
"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日股票分析报告</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", sans-serif;
    max-width: 600px;
    margin: 0 auto;
    padding: 24px 16px 60px;
    background: #f7f7f8;
    color: #1a1a1a;
  }}
  h1 {{ font-size: 22px; }}
  .group-title {{ font-size: 15px; color: #888; margin: 24px 0 8px; }}
  ul {{ list-style: none; padding: 0; margin: 0; }}
  li {{
    background: #fff;
    border-radius: 10px;
    margin-bottom: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  a {{
    display: block;
    padding: 14px 16px;
    color: #1a1a1a;
    text-decoration: none;
  }}
  a:active {{ background: #f0f0f0; }}
</style>
</head>
<body>
  <h1>📊 每日股票分析报告</h1>
  {groups}
</body>
</html>
"""


def build_index(site_dir: str):
    """扫描 site_dir 下所有 html 文件（除 index.html），按市场分组生成首页列表"""
    files = [f for f in os.listdir(site_dir) if f.endswith(".html") and f != "index.html"]
    files.sort(reverse=True)

    groups: dict[str, list[str]] = {}
    for f in files:
        # 文件名格式: 2026-06-19-a-share.html / 2026-06-19-us.html
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)\.html", f)
        if not m:
            continue
        date, market = m.groups()
        label = {"a-share": "🇨🇳 A股", "us": "🇺🇸 美股"}.get(market, market)
        groups.setdefault(label, []).append((date, f))

    group_html = []
    for label, items in groups.items():
        group_html.append(f'<div class="group-title">{html.escape(label)}</div>')
        group_html.append("<ul>")
        for date, fname in items:
            group_html.append(f'<li><a href="{fname}">{date}</a></li>')
        group_html.append("</ul>")

    index_html = INDEX_TEMPLATE.format(groups="\n".join(group_html))
    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", required=True, choices=["a-share", "us"],
                         help="市场标识，用于生成文件名后缀")
    args = parser.parse_args()

    report_glob = os.environ.get("REPORT_GLOB", "reports/*.md")
    site_dir = os.environ.get("SITE_DIR", "reports-html")

    os.makedirs(site_dir, exist_ok=True)

    report_path = find_latest_report(report_glob)
    if not report_path:
        print(f"⚠️ 未找到匹配 {report_glob} 的报告文件，跳过 HTML 生成")
        sys.exit(0)

    with open(report_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    # 新西兰时间作为文件命名日期（也可按需求改成 Asia/Shanghai）
    nz_now = datetime.now(timezone(timedelta(hours=13)))
    date_str = nz_now.strftime("%Y-%m-%d")
    out_filename = f"{date_str}-{args.market}.html"
    out_path = os.path.join(site_dir, out_filename)

    title = "A股分析报告" if args.market == "a-share" else "美股分析报告"
    body_html = markdown_to_html_body(md_text)

    page_html = PAGE_TEMPLATE.format(
        title=f"{title} {date_str}",
        generated_at=nz_now.strftime("%Y-%m-%d %H:%M:%S NZT"),
        body=body_html,
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page_html)

    build_index(site_dir)

    print(f"✅ 已生成: {out_path}")
    print(f"✅ 已更新: {os.path.join(site_dir, 'index.html')}")

    # 输出文件名供后续 GitHub Actions 步骤使用（GITHUB_OUTPUT）
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"report_filename={out_filename}\n")


if __name__ == "__main__":
    main()
