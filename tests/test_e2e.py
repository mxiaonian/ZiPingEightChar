"""端到端：subprocess 调 scripts/cast_chart.py（设计文档 §4.10 / §5）。

退出码约定：0 成功；2 输入不可用（地点/格式）；3 库内部错误。
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
CAST_CHART = SCRIPTS_DIR / "cast_chart.py"


def run_cast(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SCRIPTS_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, str(CAST_CHART), *args],
        cwd=str(SCRIPTS_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


class CastChartE2ETest(unittest.TestCase):
    def test_chengdu_morning_chart(self):
        """张三 男 1990-05-14 08:30 四川省成都市 → 正常出盘（巳月辛巳）。"""
        r = run_cast(
            "--name", "张三", "--gender", "男",
            "--birth", "1990-05-14 08:30", "--place", "四川省成都市",
        )
        self.assertEqual(r.returncode, 0, f"stderr:\n{r.stderr}")
        for marker in ("## 四柱", "## 大运", "## 排盘审计", "辛巳"):
            self.assertIn(marker, r.stdout)

    def test_beijing_late_zi_hint(self):
        """李四 女 1990-01-15 23:30 北京市 → 真太阳时约 23:06，须含晚子时提示。

        取 1 月而非 6 月：1990 年北京处于夏令时，6 月的钟表 23:30 会被拉回 22 点。
        """
        r = run_cast(
            "--name", "李四", "--gender", "女",
            "--birth", "1990-01-15 23:30", "--place", "北京市",
        )
        self.assertEqual(r.returncode, 0, f"stderr:\n{r.stderr}")
        self.assertIn("晚子时", r.stdout)

    def test_unresolvable_place_exit_2(self):
        """王五 男 1990-01-01 12:00 火星 → LocationError，退出码 2。"""
        r = run_cast(
            "--name", "王五", "--gender", "男",
            "--birth", "1990-01-01 12:00", "--place", "火星",
        )
        self.assertEqual(r.returncode, 2,
                         f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        self.assertIn("ERROR", r.stderr)


if __name__ == "__main__":
    unittest.main()
