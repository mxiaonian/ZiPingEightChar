"""运行环境守卫（scripts/_runtime_guard.py）：版本判定文案、import 时拦截、入口脚本接线。

import 时拦截用子进程模拟：伪造 sys.version_info = (3, 9, 6) 后再 import，
守卫应打印中文报错并以退出码 3 结束进程。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _runtime_guard as guard

ENTRY_SCRIPTS = ("cast_chart.py", "chart_shot.py", "memory_lookup.py",
                 "memory_save.py", "query_shensha.py", "self_update.py",
                 "share_export.py", "share_push.py")


def run_with_fake_py39(code: str) -> subprocess.CompletedProcess:
    """在子进程中把 sys.version_info 伪造成 3.9.6 后执行 code。"""
    prefix = "import sys, runpy; sys.version_info = (3, 9, 6); "
    return subprocess.run([sys.executable, "-c", prefix + code],
                          capture_output=True, text=True, timeout=60)


class TestVersionError:
    def test_current_interpreter_passes(self):
        assert guard.version_error() is None

    def test_py39_denied_with_chinese_message(self):
        msg = guard.version_error((3, 9, 6))
        assert msg is not None
        assert "Python 3.10" in msg
        assert "3.9.6" in msg
        assert sys.executable in msg

    def test_boundary_versions(self):
        assert guard.version_error((3, 10, 0)) is None
        assert guard.version_error((4, 0, 0)) is None
        assert guard.version_error((3, 8, 10)) is not None
        assert guard.version_error((2, 7, 18)) is not None


class TestImportTimeGuard:
    def test_import_denied_exits_3(self):
        cp = run_with_fake_py39(
            f"sys.path.insert(0, {str(SCRIPTS)!r}); import _runtime_guard")
        assert cp.returncode == 3
        assert "Python 3.10" in cp.stderr

    def test_import_allowed_is_silent(self):
        cp = subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import _runtime_guard"],
            capture_output=True, text=True, timeout=60)
        assert cp.returncode == 0
        assert cp.stderr == ""

    def test_entry_script_intercepts_before_deep_error(self):
        """chart_shot.py 在 3.9 下原本 def 期即 TypeError；接线后守卫先拦截，报错清晰。"""
        cp = run_with_fake_py39(
            f"sys.argv = ['chart_shot.py', 'x.html']; "
            f"runpy.run_path({str(SCRIPTS / 'chart_shot.py')!r}, run_name='__main__')")
        assert cp.returncode == 3
        assert "Python 3.10" in cp.stderr
        assert "TypeError" not in cp.stderr


class TestEntryScriptsWired:
    def test_every_entry_script_imports_guard(self):
        for name in ENTRY_SCRIPTS:
            src = (SCRIPTS / name).read_text(encoding="utf-8")
            assert "import _runtime_guard" in src, f"{name} 未接入 _runtime_guard"
