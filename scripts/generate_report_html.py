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


def classify_reports(report_glob: str) -> dict:
    """
    扫描 reports/ 目录下所有 Markdown 文件，分成两类，每类各取最新一份：
      - 'stock':  个股分析报告
      - 'market': 大盘复盘报告

    返回: {'stock': 路径或None, 'market': 路径或None}
    """
    files = glob.glob(report_glob)
    if not files:
        return {"stock": None, "market": None}

    MARKET_REVIEW_MARKERS = ["大盘复盘", "Market Review", "市场复盘"]

    files.sort(key=os.path.getmtime, reverse=True)

    result = {"stock": None, "market": None}
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                head = fp.read(500)
        except Exception:
            head = ""

        is_market_review = any(marker in head for marker in MARKET_REVIEW_MARKERS)
        key = "market" if is_market_review else "stock"

        # 每类只取最新的一份（files 已按修改时间倒序，第一次命中即为最新）
        if result[key] is None:
            result[key] = f

    return result


def render_inline(text: str) -> str:
    """处理行内格式：**加粗**、*斜体*、`代码`"""
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def is_table_separator(line: str) -> bool:
    """判断是否是 Markdown 表格分隔行，如 |---|---|"""
    return bool(re.match(r"^\|[-:\s|]+\|$", line.strip()))


def parse_table_row(line: str) -> list:
    """把 | a | b | c | 解析成 ['a', 'b', 'c']"""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def markdown_to_html_body(md_text: str) -> str:
    """
    Markdown -> HTML 转换（不引入第三方依赖）。
    支持: # 标题, **加粗**, *斜体*, `代码`, > 引用, 表格, 换行
    """
    lines = md_text.split("\n")
    html_lines = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # 检测表格：当前行是表格行，下一行是分隔行
        if (line.strip().startswith("|") and
                i + 1 < len(lines) and
                is_table_separator(lines[i + 1])):

            # 表头
            headers = parse_table_row(line)
            i += 2  # 跳过分隔行

            table_html = ['<div class="table-wrap"><table>']
            table_html.append("<thead><tr>")
            for h in headers:
                table_html.append(f"<th>{render_inline(h)}</th>")
            table_html.append("</tr></thead>")
            table_html.append("<tbody>")

            # 数据行
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = parse_table_row(lines[i].rstrip())
                table_html.append("<tr>")
                for c in cells:
                    table_html.append(f"<td>{render_inline(c)}</td>")
                table_html.append("</tr>")
                i += 1

            table_html.append("</tbody></table></div>")
            html_lines.append("\n".join(table_html))
            continue

        # 普通行处理
        if line.startswith("### "):
            html_lines.append(f"<h3>{render_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{render_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{render_inline(line[2:])}</h1>")
        elif line.startswith("> "):
            html_lines.append(f"<blockquote>{render_inline(line[2:])}</blockquote>")
        elif line.strip() == "":
            html_lines.append("<br>")
        else:
            escaped = render_inline(line)
            html_lines.append(f"<p>{escaped}</p>")

        i += 1

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
  .table-wrap {{ overflow-x: auto; margin: 16px 0; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 8px 12px; text-align: left; white-space: nowrap; }}
  th {{ background: #f0f4ff; color: #2563eb; font-weight: 600; }}
  tr:nth-child(even) {{ background: #f9fafb; }}
  code {{ background: #f3f4f6; padding: 2px 5px; border-radius: 3px; font-size: 13px; }}
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
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="icon-192.png">
<meta name="theme-color" content="#2563eb">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="股票报告">
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
  <script>
    if ('serviceWorker' in navigator) {{
      navigator.serviceWorker.register('sw.js').catch(function(err) {{
        console.log('Service worker registration failed:', err);
      }});
    }}
  </script>
</body>
</html>
"""


def ensure_pwa_assets(site_dir: str):
    """确保 PWA 必需的静态文件存在于网站目录中（manifest, service worker, 图标）"""
    import shutil

    # PWA 资源文件存放在仓库的固定位置（与本脚本同目录的 pwa/ 子文件夹）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pwa_source_dir = os.path.join(script_dir, "pwa")

    pwa_files = ["manifest.json", "sw.js", "icon-192.png", "icon-512.png"]

    for fname in pwa_files:
        src = os.path.join(pwa_source_dir, fname)
        dst = os.path.join(site_dir, fname)
        if os.path.exists(src):
            shutil.copy2(src, dst)
        else:
            print(f"⚠️ 未找到 PWA 资源文件: {src}（跳过，PWA 安装功能可能不完整）")


def build_index(site_dir: str):
    """扫描 site_dir 下所有 html 文件（除 index.html），按市场+类型分组生成首页列表"""
    files = [f for f in os.listdir(site_dir) if f.endswith(".html") and f != "index.html"]
    files.sort(reverse=True)

    groups: dict[str, list[tuple]] = {}
    for f in files:
        # 文件名格式: 2026-06-19-a-share-stock.html / 2026-06-19-us-market.html
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(a-share|us)-(stock|market)\.html", f)
        if not m:
            continue
        date, market, report_type = m.groups()
        market_label = {"a-share": "🇨🇳 A股", "us": "🇺🇸 美股"}.get(market, market)
        type_label = {"stock": "个股分析", "market": "大盘复盘"}.get(report_type, report_type)
        group_key = f"{market_label} · {type_label}"
        groups.setdefault(group_key, []).append((date, f))

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


def render_report_page(md_path: str, market: str, report_type: str, site_dir: str, nz_now) -> str:
    """把单个 Markdown 报告渲染成 HTML 页面，返回生成的文件名"""
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    date_str = nz_now.strftime("%Y-%m-%d")
    out_filename = f"{date_str}-{market}-{report_type}.html"
    out_path = os.path.join(site_dir, out_filename)

    market_label = "A股" if market == "a-share" else "美股"
    type_label = "个股分析" if report_type == "stock" else "大盘复盘"
    title = f"{market_label}{type_label}报告"

    body_html = markdown_to_html_body(md_text)

    page_html = PAGE_TEMPLATE.format(
        title=f"{title} {date_str}",
        generated_at=nz_now.strftime("%Y-%m-%d %H:%M:%S NZT"),
        body=body_html,
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page_html)

    print(f"✅ 已生成: {out_path}")
    return out_filename


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", required=True, choices=["a-share", "us"],
                         help="市场标识，用于生成文件名前缀")
    args = parser.parse_args()

    report_glob = os.environ.get("REPORT_GLOB", "reports/*.md")
    site_dir = os.environ.get("SITE_DIR", "reports-html")

    os.makedirs(site_dir, exist_ok=True)

    classified = classify_reports(report_glob)

    if not classified["stock"] and not classified["market"]:
        print(f"⚠️ 未找到匹配 {report_glob} 的报告文件，跳过 HTML 生成")
        sys.exit(0)

    nz_now = datetime.now(timezone(timedelta(hours=13)))

    generated_filenames = {}

    if classified["stock"]:
        fname = render_report_page(classified["stock"], args.market, "stock", site_dir, nz_now)
        generated_filenames["stock"] = fname
    else:
        print("⚠️ 未找到个股分析报告，跳过该部分")

    if classified["market"]:
        fname = render_report_page(classified["market"], args.market, "market", site_dir, nz_now)
        generated_filenames["market"] = fname
    else:
        print("⚠️ 未找到大盘复盘报告，跳过该部分")

    build_index(site_dir)
    ensure_pwa_assets(site_dir)

    print(f"✅ 已更新: {os.path.join(site_dir, 'index.html')}")

    # 输出文件名供后续 GitHub Actions 步骤使用（GITHUB_OUTPUT）
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            if "stock" in generated_filenames:
                f.write(f"stock_report_filename={generated_filenames['stock']}\n")
            if "market" in generated_filenames:
                f.write(f"market_report_filename={generated_filenames['market']}\n")


if __name__ == "__main__":
    main()
