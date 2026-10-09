"""share/ 脱敏共建：导出脱敏、完整度门槛、推送计励幂等（本地 bare git 仓库当远端，无网络）。"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
EXPORT = SCRIPTS_DIR / "share_export.py"
PUSH = SCRIPTS_DIR / "share_push.py"

sys.path.insert(0, str(SCRIPTS_DIR))
import _license_gate as gate
import _memory_store as store

PILLARS = ["庚午", "辛巳", "己卯", "戊辰"]
BIRTH = "1990-05-14 08:30"
PLACE = "四川省成都市"

git = pytest.mark.skipif(shutil.which("git") is None, reason="无 git")


def run(script, *args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SCRIPTS_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, timeout=120, env=env)


def make_archive(mem_root: Path, feedback: str | None = None) -> Path:
    """造一份手工档案：四柱/大运/关注方向齐全，反馈小节可定制。"""
    meta = {"name": "张三", "gender": "男", "birth_clock": BIRTH,
            "birthplace": PLACE, "true_solar_time": "1990-05-14 08:23",
            "pillars": PILLARS, "day_master": "己",
            "created_at": "2026-10-01 10:00", "updated_at": "2026-10-08 15:00"}
    body = (
        "# 档案：张三（男）\n\n"
        "## 盘面\n\n"
        "# 命盘：张三\n\n"
        "## 大运\n\n"
        "- 排法：顺行；起运：7 岁 8 个月 1 天（7.67 岁）\n"
        "- 第 1 步：壬午（7.67 岁起，1998 年）\n"
        "- 第 2 步：癸未（17.67 岁起，2008 年）\n"
        "- 第 3 步：甲申（27.67 岁起，2018 年）\n\n"
        "## 小运\n\n（无）\n\n"
        "## 主要关注方向\n\n- 婚姻与事业走向\n\n"
        "## 归纳\n\n- 性格：未断\n- 身体：未断\n- 事业：未断\n- 感情：未断\n- 婚姻：未断\n\n"
        "## 流年大事\n\n（未记录）\n\n"
        "## 反馈与澄清\n\n"
        + (feedback if feedback is not None else
           "- 【已核实】2018 年升职，跳槽到外企\n- 【未核实】2020 年感情波动\n")
    )
    arch_dir = mem_root / "archives"
    arch_dir.mkdir(parents=True, exist_ok=True)
    path = arch_dir / store.archive_name(
        PILLARS, "男", store.key_hash(BIRTH, PLACE, "男"))
    path.write_text(store.dump_frontmatter(meta) + body, encoding="utf-8")
    return path


@pytest.fixture
def share_root(tmp_path):
    return tmp_path / "share"


class TestExport:
    def test_package_is_sanitized(self, tmp_path, share_root):
        arch = make_archive(tmp_path / "memory")
        r = run(EXPORT, "--archive", str(arch), "--share-root", str(share_root))
        assert r.returncode == 0, r.stderr
        out = Path(r.stdout.strip())
        assert out.parent == share_root / "pending"
        text = out.read_text("utf-8")
        pkg = json.loads(text)

        # 脱敏：不含姓名、出生分钟/钟表时间、省以下地域
        assert "name" not in pkg
        assert "张三" not in text
        assert "08:30" not in text and "08:23" not in text
        assert "成都市" not in text
        assert "birth_clock" not in pkg and "birthplace" not in pkg

        # 结构字段
        assert pkg["schema"] == "share/v1"
        assert pkg["gender"] == "男"
        assert pkg["pillars"] == PILLARS
        assert pkg["birth_date"] == "1990-05-14"
        assert pkg["birth_shichen"] == "辰"
        assert pkg["region_province"] == "四川省"
        assert [l["pillar"] for l in pkg["luck_pillars"]] == ["壬午", "癸未", "甲申"]
        assert pkg["luck_pillars"][0]["start_year"] == 1998
        assert pkg["focus_categories"] == ["婚姻", "事业"]
        assert {f["year"] for f in pkg["feedback"]} == {2018, 2020}
        assert {f["status"] for f in pkg["feedback"]} == {"已核实", "未核实"}
        assert all(f["category"] for f in pkg["feedback"])
        # 盘 hash = sha1(四柱+出生地) 前 8，文件名即 hash
        assert out.stem == pkg["chart_hash"]
        assert len(pkg["chart_hash"]) == 8

    def test_lookup_by_birth_place_gender(self, tmp_path, share_root):
        make_archive(tmp_path / "memory")
        r = run(EXPORT, "--birth", BIRTH, "--place", PLACE, "--gender", "男",
                "--memory-root", str(tmp_path / "memory"),
                "--share-root", str(share_root))
        assert r.returncode == 0, r.stderr
        assert (share_root / "pending").glob("*.json")

    def test_completeness_gate_refuses_without_feedback(self, tmp_path, share_root):
        arch = make_archive(tmp_path / "memory", feedback="（无）\n")
        r = run(EXPORT, "--archive", str(arch), "--share-root", str(share_root))
        assert r.returncode == 2
        assert "反馈事件" in r.stderr
        assert not list((share_root / "pending").glob("*.json"))

    def test_archive_not_found(self, tmp_path, share_root):
        r = run(EXPORT, "--archive", str(tmp_path / "nope.md"),
                "--share-root", str(share_root))
        assert r.returncode == 2


@git
class TestPush:
    @pytest.fixture
    def skill(self, tmp_path):
        """假技能根：share/ 骨架 + 两个 bare 远端 + 授权状态（5 次）。"""
        root = tmp_path / "skill"
        (root / "share" / "pending").mkdir(parents=True)
        (root / "share" / "pushed").mkdir(parents=True)
        remotes = {}
        for name in ("github", "gitea"):
            bare = tmp_path / f"{name}.git"
            subprocess.run(["git", "init", "--bare", str(bare)],
                           capture_output=True, check=True)
            remotes[f"{name}_remote"] = str(bare)
        (root / "share" / "config.json").write_text(
            json.dumps(remotes, ensure_ascii=False), "utf-8")
        gate.write_state(root, copy_id="LY-20261009-TEST",
                         licensee="测试", max_uses=5)
        return root

    def _export_into(self, skill_root, tmp_path):
        arch = make_archive(tmp_path / "memory")
        r = run(EXPORT, "--archive", str(arch),
                "--share-root", str(skill_root / "share"))
        assert r.returncode == 0, r.stderr
        return Path(r.stdout.strip())

    def test_push_grants_uses_and_moves_package(self, skill, tmp_path):
        pkg = self._export_into(skill, tmp_path)
        r = run(PUSH, "--root", str(skill))
        assert r.returncode == 0, r.stderr
        assert not pkg.exists()
        assert (skill / "share" / "pushed" / pkg.name).is_file()
        st = json.loads((skill / "data" / ".license.json").read_text("utf-8"))
        assert st["remaining_uses"] == 15  # 5 + 10
        assert st["granted_archives"] == [pkg.stem]
        # 远端确实收到提交
        log = subprocess.run(
            ["git", "--git-dir", str(tmp_path / "github.git"), "log", "--oneline"],
            capture_output=True, text=True)
        assert f"share: {pkg.stem}" in log.stdout

    def test_push_same_chart_twice_grants_once(self, skill, tmp_path):
        pkg = self._export_into(skill, tmp_path)
        assert run(PUSH, "--root", str(skill)).returncode == 0
        # 同一盘再次导出推送：仍成功移走，但不重复计励
        pkg2 = self._export_into(skill, tmp_path)
        assert pkg2.name == pkg.name
        r = run(PUSH, "--root", str(skill))
        assert r.returncode == 0, r.stderr
        assert "不重复" in r.stdout
        st = json.loads((skill / "data" / ".license.json").read_text("utf-8"))
        assert st["remaining_uses"] == 15
        assert st["granted_archives"] == [pkg.stem]

    def test_push_failure_keeps_pending(self, skill):
        bad = {"github_remote": str(skill / "no-such-repo.git"),
               "gitea_remote": ""}
        (skill / "share" / "config.json").write_text(
            json.dumps(bad, ensure_ascii=False), "utf-8")
        pkg = skill / "share" / "pending" / "deadbeef.json"
        pkg.write_text(json.dumps({"schema": "share/v1",
                                   "chart_hash": "deadbeef"}), "utf-8")
        r = run(PUSH, "--root", str(skill))
        assert r.returncode == 3
        assert pkg.is_file()  # 失败保留 pending
        st = json.loads((skill / "data" / ".license.json").read_text("utf-8"))
        assert st["remaining_uses"] == 5  # 未计励

    def test_no_remote_configured(self, tmp_path):
        root = tmp_path / "skill"
        (root / "share" / "pending").mkdir(parents=True)
        (root / "share" / "config.json").write_text(
            json.dumps({"github_remote": "", "gitea_remote": ""}), "utf-8")
        (root / "share" / "pending" / "abc12345.json").write_text("{}", "utf-8")
        r = run(PUSH, "--root", str(root))
        assert r.returncode == 3
        assert (root / "share" / "pending" / "abc12345.json").is_file()

    def test_env_overrides_config(self, skill, tmp_path):
        # config 远端写死为坏地址，环境变量指向好远端
        (skill / "share" / "config.json").write_text(json.dumps(
            {"github_remote": str(skill / "bad.git"), "gitea_remote": ""}), "utf-8")
        good = tmp_path / "env.git"
        subprocess.run(["git", "init", "--bare", str(good)],
                       capture_output=True, check=True)
        pkg = skill / "share" / "pending" / "c0ffee11.json"
        pkg.write_text(json.dumps({"schema": "share/v1",
                                   "chart_hash": "c0ffee11"}), "utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SCRIPTS_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        env["ZIPING_SHARE_GITHUB_REMOTE"] = str(good)
        r = subprocess.run([sys.executable, str(PUSH), "--root", str(skill)],
                           capture_output=True, text=True, timeout=120, env=env)
        assert r.returncode == 0, r.stderr
        assert (skill / "share" / "pushed" / "c0ffee11.json").is_file()
