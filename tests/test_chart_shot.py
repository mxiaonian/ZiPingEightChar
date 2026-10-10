"""chart_shot.py 与 cast_chart --shot：HTML → PNG 截图的分级回退与优雅失败。"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import chart_shot  # noqa: E402

CHROME_OK = Path(chart_shot.CHROME).is_file()
try:
    import playwright  # noqa: F401
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False
SHOT_OK = CHROME_OK or PLAYWRIGHT_OK

HTML = "<!DOCTYPE html><html><body><h1>命盘</h1></body></html>"


class ShootUnitTest(unittest.TestCase):
    def test_missing_html_exit_2(self):
        r = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts" / "chart_shot.py"),
             "/nonexistent/x.html"], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 2)
        self.assertIn("ERROR", r.stderr)

    def test_no_tools_fails_gracefully(self):
        """playwright 与 Chrome 都不可用时：shoot 返回 None，CLI 退出码 2 并给提示。"""
        with tempfile.TemporaryDirectory() as td:
            html = Path(td) / "p.html"
            html.write_text(HTML, encoding="utf-8")
            with mock.patch.object(chart_shot, "_shot_playwright",
                                   return_value=False), \
                 mock.patch.object(chart_shot, "_shot_chrome",
                                   return_value=False):
                self.assertIsNone(chart_shot.shoot(html))
                self.assertFalse(html.with_suffix(".png").exists())
                with mock.patch.object(sys, "argv",
                                       ["chart_shot.py", str(html)]):
                    with mock.patch("sys.stderr") as err:
                        self.assertEqual(chart_shot.main(), 2)
                    err.write.assert_called()

    def test_content_height_bounds(self):
        """高度估算不越界：空页夹到下限，超长页夹到上限。"""
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "e.html"
            empty.write_text(HTML, encoding="utf-8")
            self.assertEqual(chart_shot._content_height(empty), 1300)
            big = Path(td) / "b.html"
            big.write_text(
                '<div class="strip">' + '<div class="cell"></div>' * 5000
                + "</div>", encoding="utf-8")
            self.assertEqual(chart_shot._content_height(big), 4200)


@unittest.skipUnless(SHOT_OK, "环境无 playwright 与 Chrome，跳过真实截图")
class ShootRealTest(unittest.TestCase):
    def test_real_png(self):
        """真实截图：PNG 非空、宽 2200（1100 窗口 × 2 倍分辨率）。"""
        import struct
        with tempfile.TemporaryDirectory() as td:
            html = Path(td) / "p.html"
            html.write_text(HTML, encoding="utf-8")
            png = chart_shot.shoot(html)
            self.assertIsNotNone(png)
            data = png.read_bytes()
            self.assertGreater(len(data), 1000)
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            w, _h = struct.unpack(">II", data[16:24])
            self.assertEqual(w, 2200)

    def test_cli_success(self):
        with tempfile.TemporaryDirectory() as td:
            html = Path(td) / "p.html"
            html.write_text(HTML, encoding="utf-8")
            out = Path(td) / "o.png"
            r = subprocess.run(
                [sys.executable, str(SKILL_ROOT / "scripts" / "chart_shot.py"),
                 str(html), "-o", str(out)],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(str(out), r.stdout)
            self.assertGreater(out.stat().st_size, 0)


@unittest.skipUnless(SHOT_OK, "环境无 playwright 与 Chrome，跳过 --shot 端到端")
class CastShotE2ETest(unittest.TestCase):
    def test_shot_flag_outputs_paths(self):
        with tempfile.TemporaryDirectory() as td:
            html = Path(td) / "p.html"
            r = subprocess.run(
                [sys.executable, str(SKILL_ROOT / "scripts" / "cast_chart.py"),
                 "--name", "张三", "--gender", "男", "--birth", "1990-05-14 08:30",
                 "--place", "四川省成都市", "--html", str(html), "--shot"],
                capture_output=True, text=True, timeout=120,
                cwd=str(SKILL_ROOT / "scripts"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.startswith("# 命盘：张三"))
            self.assertIn(f"HTML 盘面：{html.resolve()}", r.stdout)
            png = html.with_suffix(".png")
            self.assertIn(f"盘面截图：{png.resolve()}", r.stdout)
            self.assertGreater(png.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
