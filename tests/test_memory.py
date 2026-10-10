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

# 晚子时案例：真太阳时落于 23:00–24:00，子初/子正换日四柱不同
WANZI = ["--name", "李四", "--gender", "女",
         "--birth", "1996-12-08 00:30", "--place", "四川省乐山市"]


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


class TestUpdateChart:
    """换盘（--update-chart）：工作盘唯一——盘面段整体替换为新盘，frontmatter
    与文件名同步，其余小节保留；旧盘信息由使用方记入反馈与澄清。"""

    def test_zizheng_replaces_chart_and_renames(self, tmp_path):
        r1 = run(SAVE, tmp_path, *WANZI)
        assert r1.returncode == 0, f"stderr:\n{r1.stderr}"
        path = Path(r1.stdout.strip())
        assert "丙子庚子庚辰丙子" in path.name  # 默认子初换日盘

        # 模拟核对后的回写 + 固定 created_at
        text = path.read_text(encoding="utf-8")
        text = text.replace("（无）", "- 【已核实】2016 年离乡赴厦门读大学。")
        text = re.sub(r'^created_at:.*$', 'created_at: "2000-01-01 00:00"',
                      text, count=1, flags=re.M)
        path.write_text(text, encoding="utf-8")

        # 用户确认子正换日：重排替换盘面段，日柱/时柱变 → 改新主键名
        r2 = run(SAVE, tmp_path, "--update-chart", str(path),
                 "--day-boundary", "子正")
        assert r2.returncode == 0, f"stderr:\n{r2.stderr}"
        assert "日柱 庚辰→己卯" in r2.stderr and "时柱 丙子→甲子" in r2.stderr
        assert "待复核" in r2.stderr  # 变动柱影响条目提示复核
        new_path = Path(r2.stdout.strip())
        assert new_path != path and not path.exists()
        assert "丙子庚子己卯甲子" in new_path.name
        assert list((tmp_path / "archives").glob("*.md")) == [new_path]

        text = new_path.read_text(encoding="utf-8")
        meta = read_meta(text)
        assert meta["pillars"] == '["丙子", "庚子", "己卯", "甲子"]'
        assert meta["day_master"] == "己"
        assert meta["created_at"] == "2000-01-01 00:00"  # 保留
        # 盘面段只剩新盘：日界审计与晚子时警示均为子正口径，无旧盘残留
        assert "- 日界规则：子正换日（真太阳时 00:00）" in text
        assert "已按「子正换日」定盘" in text
        assert text.count("# 命盘") == 1
        chart_section = text.split("## 盘面")[1].split("## 主要关注方向")[0]
        assert "日柱：己卯" in chart_section and "日柱：庚辰" not in chart_section
        # 其余小节保留
        assert "- 【已核实】2016 年离乡赴厦门读大学。" in text

    def test_birth_correction_updates_meta(self, tmp_path):
        r1 = run(SAVE, tmp_path, *ZHANGSAN)
        assert r1.returncode == 0, f"stderr:\n{r1.stderr}"
        path = Path(r1.stdout.strip())

        r2 = run(SAVE, tmp_path, "--update-chart", str(path),
                 "--birth", "1990-05-14 10:30")
        assert r2.returncode == 0, f"stderr:\n{r2.stderr}"
        assert "时柱" in r2.stderr and "待复核" in r2.stderr
        new_path = Path(r2.stdout.strip())
        assert new_path != path and not path.exists()  # hash6 随 birth 变
        meta = read_meta(new_path.read_text(encoding="utf-8"))
        assert meta["birth_clock"] == "1990-05-14 10:30"

    def test_same_chart_keeps_filename(self, tmp_path):
        r1 = run(SAVE, tmp_path, *ZHANGSAN)
        assert r1.returncode == 0, f"stderr:\n{r1.stderr}"
        path = Path(r1.stdout.strip())
        r2 = run(SAVE, tmp_path, "--update-chart", str(path))
        assert r2.returncode == 0, f"stderr:\n{r2.stderr}"
        assert Path(r2.stdout.strip()) == path  # 四柱未变，文件名不动
        assert "待复核" not in r2.stderr

    def test_conflict_refuses_overwrite(self, tmp_path):
        run(SAVE, tmp_path, *WANZI)
        olds = list((tmp_path / "archives").glob("*.md"))
        assert len(olds) == 1
        old = olds[0]
        r = run(SAVE, tmp_path, "--update-chart", str(old),
                "--day-boundary", "子正")
        assert r.returncode == 0, f"stderr:\n{r.stderr}"
        # 重新建子初盘档案，再换子正 → 目标已存在，拒绝覆盖
        run(SAVE, tmp_path, *WANZI)
        r = run(SAVE, tmp_path, "--update-chart", str(old),
                "--day-boundary", "子正")
        assert r.returncode == 2
        assert "已存在" in r.stderr
        assert len(list((tmp_path / "archives").glob("*.md"))) == 2

    def test_missing_archive_exit_2(self, tmp_path):
        r = run(SAVE, tmp_path, "--update-chart",
                str(tmp_path / "archives" / "nope.md"))
        assert r.returncode == 2

    def test_rejects_name_gender_overrides(self, tmp_path):
        r1 = run(SAVE, tmp_path, *ZHANGSAN)
        assert r1.returncode == 0, f"stderr:\n{r1.stderr}"
        path = r1.stdout.strip()
        r = run(SAVE, tmp_path, "--update-chart", path, "--name", "王五")
        assert r.returncode == 2
