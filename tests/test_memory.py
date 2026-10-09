"""档案（memory/）：save → lookup 往返、同主键更新保留正文小节、无匹配输出。

脚本以 --memory-root / ZIPING_MEMORY_ROOT 覆盖档案根目录，测试用 tmp_path 隔离。
"""
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
SAVE = SCRIPTS_DIR / "memory_save.py"
LOOKUP = SCRIPTS_DIR / "memory_lookup.py"

ZHANGSAN = ["--name", "张三", "--gender", "男",
            "--birth", "1990-05-14 08:30", "--place", "四川省成都市"]


def run(script, mem_root, *args, use_env=False):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SCRIPTS_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, str(script), *args]
    if use_env:
        env["ZIPING_MEMORY_ROOT"] = str(mem_root)
    else:
        cmd += ["--memory-root", str(mem_root)]
    return subprocess.run(cmd, cwd=str(SCRIPTS_DIR), env=env,
                          capture_output=True, text=True, timeout=120)


def read_meta(text: str) -> dict:
    """受限 frontmatter 解析：仅取测试断言所需的标量字段。"""
    lines = text.splitlines()
    assert lines[0] == "---"
    meta = {}
    for ln in lines[1:]:
        if ln == "---":
            break
        k, _, v = ln.partition(":")
        meta[k.strip()] = v.strip().strip('"')
    return meta


class TestSaveLookupRoundtrip:
    def test_save_then_lookup_by_name_and_pillars(self, tmp_path):
        r = run(SAVE, tmp_path, *ZHANGSAN)
        assert r.returncode == 0, f"stderr:\n{r.stderr}"
        path = Path(r.stdout.strip())
        assert path.is_file()
        assert path.parent == tmp_path / "archives"
        text = path.read_text(encoding="utf-8")
        # schema：frontmatter + 固定小节 + 嵌入命盘
        meta = read_meta(text)
        assert meta["name"] == "张三" and meta["gender"] == "男"
        assert meta["birth_clock"] == "1990-05-14 08:30"
        assert meta["birthplace"] == "四川省成都市"
        assert meta["created_at"] and meta["updated_at"]
        for section in ("## 盘面", "## 主要关注方向", "## 归纳",
                        "## 流年大事", "## 反馈与澄清"):
            assert section in text
        assert "## 四柱" in text  # 盘面嵌入命盘全文
        assert "- 性格：未断" in text

        # 按姓名检索命中（参数覆盖 memory 根目录）
        r = run(LOOKUP, tmp_path, "--name", "张三")
        assert r.returncode == 0, f"stderr:\n{r.stderr}"
        assert str(path) in r.stdout and "张三" in r.stdout

        # 按四柱检索命中（环境变量覆盖 memory 根目录）
        pillars = meta["pillars"].strip("[]").replace('"', "").replace(",", "")
        r = run(LOOKUP, tmp_path, "--pillars", pillars, use_env=True)
        assert r.returncode == 0, f"stderr:\n{r.stderr}"
        assert str(path) in r.stdout

        # 出生信息组合检索，空白容错
        r = run(LOOKUP, tmp_path, "--birth", "1990-05-14   08:30",
                "--place", " 四川省成都市 ", "--gender", "男")
        assert r.returncode == 0 and str(path) in r.stdout


class TestSameKeyUpdate:
    def test_update_preserves_body_sections(self, tmp_path):
        r1 = run(SAVE, tmp_path, *ZHANGSAN)
        assert r1.returncode == 0, f"stderr:\n{r1.stderr}"
        path = Path(r1.stdout.strip())

        # 模拟解释完成后的回写：改归纳、加反馈、固定 created_at 以便断言
        text = path.read_text(encoding="utf-8")
        text = text.replace("- 性格：未断", "- 性格：沉稳内敛【已核实】")
        text = text.replace("（无）", "- 【已证伪】断 2024 年升职；实际为调岗未升。")
        text = re.sub(r'^created_at:.*$', 'created_at: "2000-01-01 00:00"',
                      text, count=1, flags=re.M)
        path.write_text(text, encoding="utf-8")

        # 同主键再次建档：同一文件、盘面刷新、其余小节保留、created_at 不动
        r2 = run(SAVE, tmp_path, *ZHANGSAN)
        assert r2.returncode == 0, f"stderr:\n{r2.stderr}"
        assert Path(r2.stdout.strip()) == path
        assert list((tmp_path / "archives").glob("*.md")) == [path]
        text = path.read_text(encoding="utf-8")
        assert "- 性格：沉稳内敛【已核实】" in text
        assert "【已证伪】断 2024 年升职；实际为调岗未升。" in text
        assert "## 四柱" in text  # 盘面仍为完整命盘
        assert text.count("# 命盘") == 1  # 旧盘面整体替换，无残留重复
        meta = read_meta(text)
        assert meta["created_at"] == "2000-01-01 00:00"
        assert meta["updated_at"] != meta["created_at"]


class TestLookupNoMatch:
    def test_no_match_exit_0(self, tmp_path):
        r = run(LOOKUP, tmp_path, "--name", "不存在的人")
        assert r.returncode == 0, f"stderr:\n{r.stderr}"
        assert "无档案" in r.stdout

    def test_no_condition_exit_2(self, tmp_path):
        r = run(LOOKUP, tmp_path)
        assert r.returncode == 2
