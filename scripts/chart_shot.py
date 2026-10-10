#!/usr/bin/env python3
"""HTML 盘面 → PNG 截图。

用法：
    python chart_shot.py <html路径> [-o 输出png路径]

截图分级回退：环境装有 playwright 则优先（file:// 全页截图，2 倍分辨率）；
否则用 macOS Chrome 无头截图（固定窗口，高度按 HTML 内容估算避免截断）。
两者都不可用：退出码 2，stderr 提示直接打开 HTML。截图失败不影响排盘主流程。
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _runtime_guard  # noqa: F401  import 即检查：Python < 3.10 时中文报错退出（码 3）

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _shot_playwright(html: Path, out: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(device_scale_factor=2)
            page.goto(html.resolve().as_uri())
            page.screenshot(path=str(out), full_page=True)
            browser.close()
    except Exception:
        return False
    return out.is_file() and out.stat().st_size > 0


def _content_height(html: Path) -> int:
    """按 HTML 结构估算整页高度（px）：头卡/主表/页脚取固定高，条带按格数折行。"""
    text = html.read_text(encoding="utf-8", errors="ignore")
    height = (900 + 40 * text.count('class="warn"')
              + 150 * text.count('class="qrcard"'))
    for strip in text.split('class="strip"')[1:]:
        cells = strip.count('class="cell"')
        height += 36 + 132 * -(-cells // 9)
    return max(1300, min(height + 120, 4200))


def _shot_chrome(html: Path, out: Path) -> bool:
    if not Path(CHROME).is_file():
        return False
    try:
        r = subprocess.run(
            [CHROME, "--headless=new", f"--screenshot={out.resolve()}",
             f"--window-size=1100,{_content_height(html)}",
             "--force-device-scale-factor=2", "--hide-scrollbars",
             html.resolve().as_uri()],
            capture_output=True, timeout=60)
    except Exception:
        return False
    return r.returncode == 0 and out.is_file() and out.stat().st_size > 0


def shoot(html: Path, out: Path | None = None) -> Path | None:
    """对 HTML 盘面截图，成功返回 PNG 绝对路径，无可用工具或失败返回 None。"""
    out = out or html.with_suffix(".png")
    if _shot_playwright(html, out) or _shot_chrome(html, out):
        return out.resolve()
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="chart_shot.py",
        description="HTML 盘面 → PNG 截图（playwright 优先，Chrome 无头兜底）")
    ap.add_argument("html", help="HTML 盘面文件路径")
    ap.add_argument("-o", "--out", default=None,
                    help="输出 PNG 路径（默认与 HTML 同目录同名 .png）")
    a = ap.parse_args()
    html = Path(a.html)
    if not html.is_file():
        print(f"ERROR: 找不到 HTML 文件 {html}", file=sys.stderr)
        return 2
    png = shoot(html, Path(a.out) if a.out else None)
    if png:
        print(png)
        return 0
    print("无可用截图工具（未检测到 playwright 或 Chrome），"
          "请直接打开 HTML 文件查看盘面。", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
