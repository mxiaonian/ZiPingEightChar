"""自更新：版本比较、24h 缓存、manifest 校验拦截、apply 同步与保留区、退出码。

远端用本地临时目录伪造：VERSION / zipball / manifest 直链均以 file://
地址经 ZIPEC_VERSION_URLS / ZIPEC_ZIPBALL_URLS / ZIPEC_MANIFEST_URLS
注入，不碰真实网络。manifest 一律用测试密钥签名，UPDATE_PUBLIC_KEY_HEX
由 autouse fixture 替换为测试公钥。
"""
import base64
import hashlib
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import _update_sig
import self_update as su

# 测试专用密钥（与正式私钥无关）
TEST_SEED = bytes(range(32))
TEST_PK_HEX = _update_sig.publickey(TEST_SEED).hex()
OTHER_SEED = bytes(range(32, 64))


@pytest.fixture(autouse=True)
def _test_public_key(monkeypatch):
    monkeypatch.setattr(su, "UPDATE_PUBLIC_KEY_HEX", TEST_PK_HEX)


# ---- 造本地副本与伪造远端 ----

def make_local(tmp_path, version="3.5.0"):
    root = tmp_path / "local"
    (root / "scripts").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "scripts" / "cast_chart.py").write_text("# old\n", encoding="utf-8")
    (root / "data" / "cities.json").write_text("{}", encoding="utf-8")
    (root / "stale_legacy.py").write_text("# to be removed\n", encoding="utf-8")
    (root / "legacy").mkdir()
    (root / "legacy" / "gone.py").write_text("# to be removed\n", encoding="utf-8")
    # 保留区：更新后必须原样存活
    (root / "data" / ".license.json").write_text('{"copy_id": "x"}', encoding="utf-8")
    (root / "memory" / "archives").mkdir(parents=True)
    (root / "memory" / "archives" / "keep.md").write_text("keep", encoding="utf-8")
    (root / "share" / "pending").mkdir(parents=True)
    (root / "share" / "pending" / "keep.md").write_text("keep", encoding="utf-8")
    return root


def make_remote(tmp_path, version="3.6.0", files=None, tamper=None,
                sign_seed=TEST_SEED, zip_sig=True, sig_message=None,
                diverge_source=False):
    """造远端：zipball（带一层顶层目录，模拟 GitHub codeload）+ 远端 VERSION
    + 两个"源"目录（src_a/src_b，各存 manifest.json 与 manifest.json.sig
    直链文件，供双源交叉验证）。

    tamper=<相对路径>：先按原内容算清单哈希并签名，再篡改该文件 → 触发逐文件
    SHA256 拦截。sign_seed 控制签名密钥（换 OTHER_SEED 模拟错误私钥）。
    zip_sig=False：zip 内不放 manifest.json.sig（源目录仍放，可测单独拉取；
    配合 source_sig=False 则彻底无签名）。sig_message：改签别的内容，
    模拟 manifest 与签名不符。diverge_source=True：src_b 的 manifest 改一字节，
    模拟两源不一致。
    """
    src = tmp_path / "zipcontent" / "ZiPingEightChar-main"
    src.mkdir(parents=True)
    all_files = {"VERSION": version + "\n", **(files or {})}
    for rel, content in all_files.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    hashes = {
        rel: hashlib.sha256((src / rel).read_bytes()).hexdigest()
        for rel in all_files
    }
    manifest_bytes = (json.dumps({"version": version, "files": hashes}, indent=2)
                      + "\n").encode("utf-8")
    (src / "manifest.json").write_bytes(manifest_bytes)
    sig_b64 = base64.b64encode(
        _update_sig.sign(sign_seed, sig_message if sig_message is not None
                         else manifest_bytes)).decode("ascii") + "\n"
    if tamper:
        (src / tamper).write_text("# tampered\n", encoding="utf-8")
    if zip_sig:
        (src / "manifest.json.sig").write_text(sig_b64, encoding="utf-8")
    zip_path = tmp_path / "remote.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in sorted(src.parent.rglob("*")):
            zf.write(f, f.relative_to(src.parent))
    # 双源直链文件
    source_dirs = []
    for name in ("src_a", "src_b"):
        d = tmp_path / name
        d.mkdir()
        m = manifest_bytes
        if diverge_source and name == "src_b":
            m = m.replace(b'"files"', b'"filez"', 1)
        (d / "manifest.json").write_bytes(m)
        (d / "manifest.json.sig").write_text(sig_b64, encoding="utf-8")
        source_dirs.append(d)
    version_file = tmp_path / "REMOTE_VERSION"
    version_file.write_text(version + "\n", encoding="utf-8")
    return version_file, zip_path, source_dirs


def point_at_remote(monkeypatch, version_file, zip_path=None, source_dirs=None):
    monkeypatch.setenv("ZIPEC_VERSION_URLS", version_file.as_uri())
    if zip_path is not None:
        monkeypatch.setenv("ZIPEC_ZIPBALL_URLS", zip_path.as_uri())
    if source_dirs is not None:
        monkeypatch.setenv("ZIPEC_MANIFEST_URLS", ",".join(
            (d / "manifest.json").as_uri() for d in source_dirs))


REMOTE_FILES = {
    "scripts/cast_chart.py": "# new\n",
    "scripts/new_feature.py": "# new file\n",
    "data/cities.json": '{"new": 1}',
}


class TestVersionCompare:
    def test_parse(self):
        assert su.parse_version("3.5.0") == (3, 5, 0)
        assert su.parse_version(" 3.10.1\n") == (3, 10, 1)
        with pytest.raises(ValueError):
            su.parse_version("3.x.0")

    def test_newer_remote_marks_update(self, tmp_path, monkeypatch):
        root = make_local(tmp_path)
        vf, _, _ = make_remote(tmp_path)
        point_at_remote(monkeypatch, vf)
        assert su.cmd_check(root) == 0
        cache = json.loads((root / "data" / ".update_check.json").read_text())
        assert cache["remote_version"] == "3.6.0"
        assert cache["update_available"] is True

    def test_same_version_no_update(self, tmp_path, monkeypatch):
        root = make_local(tmp_path)
        vf, _, _ = make_remote(tmp_path, version="3.5.0")
        point_at_remote(monkeypatch, vf)
        assert su.cmd_check(root) == 0
        cache = json.loads((root / "data" / ".update_check.json").read_text())
        assert cache["update_available"] is False


class TestCacheFreshness:
    def test_fresh_cache_skips_network(self, tmp_path, monkeypatch, capsys):
        root = make_local(tmp_path)
        calls = []

        def fake_fetch(url, timeout=3):
            calls.append(url)
            return "3.6.0"

        monkeypatch.setattr(su, "_fetch_text", fake_fetch)
        assert su.cmd_check(root) == 0
        assert su.cmd_check(root) == 0
        assert len(calls) == 1  # 24h 内第二次 --check 直接读缓存
        assert "已检查过" in capsys.readouterr().out

    def test_stale_cache_refetches(self, tmp_path, monkeypatch):
        root = make_local(tmp_path)
        calls = []
        monkeypatch.setattr(
            su, "_fetch_text",
            lambda url, timeout=3: calls.append(url) or "3.6.0",
        )
        su.cmd_check(root)
        p = root / "data" / ".update_check.json"
        cache = json.loads(p.read_text())
        cache["checked_at"] = time.time() - 25 * 3600  # 人为过期
        p.write_text(json.dumps(cache), encoding="utf-8")
        assert su.cmd_check(root) == 0
        assert len(calls) == 2

    def test_notify_reads_cache_only(self, tmp_path, capsys):
        root = tmp_path / "local"
        root.mkdir()
        assert su.notify_message(root) is None  # 无缓存 → 静默
        assert su.cmd_notify(root) == 0
        assert capsys.readouterr().err == ""

    def test_notify_prints_hint(self, tmp_path, capsys):
        root = make_local(tmp_path)
        (root / "data" / ".update_check.json").write_text(json.dumps({
            "checked_at": time.time(), "local_version": "3.5.0",
            "remote_version": "3.6.0", "update_available": True,
        }), encoding="utf-8")
        msg = su.notify_message(root)
        assert "3.6.0" in msg and "--apply" in msg
        assert su.cmd_notify(root) == 0
        assert "3.6.0" in capsys.readouterr().err

    def test_refresh_cache_failure_silent(self, tmp_path, monkeypatch):
        root = make_local(tmp_path)
        def boom(url, timeout=3):
            raise OSError("network down")
        monkeypatch.setattr(su, "_fetch_text", boom)
        su.refresh_cache(root)  # 不抛
        assert not (root / "data" / ".update_check.json").exists()


class TestApply:
    def test_success_syncs_and_preserves(self, tmp_path, monkeypatch, capsys):
        root = make_local(tmp_path)
        vf, zp, dirs = make_remote(tmp_path, files=REMOTE_FILES)
        point_at_remote(monkeypatch, vf, zp, dirs)
        assert su.cmd_apply(root) == 0
        out = capsys.readouterr().out
        assert "交叉验证通过" in out and "签名校验通过" in out and "更新完成" in out
        # 清单内文件被覆盖/新增
        assert (root / "VERSION").read_text().strip() == "3.6.0"
        assert (root / "scripts" / "cast_chart.py").read_text() == "# new\n"
        assert (root / "scripts" / "new_feature.py").exists()
        assert (root / "manifest.json").exists()
        assert (root / "manifest.json.sig").exists()  # 签名随包同步到本地
        # 清单不含的本地多余文件被清理
        assert not (root / "stale_legacy.py").exists()
        assert not (root / "legacy").exists()  # 清空后的空目录一并移除
        # 保留区原样存活
        assert (root / "data" / ".license.json").read_text() == '{"copy_id": "x"}'
        assert (root / "data" / ".update_check.json").exists()
        assert (root / "memory" / "archives" / "keep.md").read_text() == "keep"
        assert (root / "share" / "pending" / "keep.md").read_text() == "keep"

    def test_tampered_file_aborts_untouched(self, tmp_path, monkeypatch, capsys):
        root = make_local(tmp_path)
        vf, zp, dirs = make_remote(tmp_path, files=REMOTE_FILES,
                                   tamper="scripts/cast_chart.py")
        point_at_remote(monkeypatch, vf, zp, dirs)
        assert su.cmd_apply(root) == 3
        assert "不符" in capsys.readouterr().err
        # 本地原样不动
        assert (root / "VERSION").read_text().strip() == "3.5.0"
        assert (root / "scripts" / "cast_chart.py").read_text() == "# old\n"
        assert (root / "stale_legacy.py").exists()
        assert not (root / "scripts" / "new_feature.py").exists()

    def test_already_latest_exit_2(self, tmp_path, monkeypatch, capsys):
        root = make_local(tmp_path)
        vf, zp, _ = make_remote(tmp_path, version="3.5.0")
        point_at_remote(monkeypatch, vf, zp)
        assert su.cmd_apply(root) == 2
        assert "无需更新" in capsys.readouterr().out

    def test_missing_local_version_exit_2(self, tmp_path):
        root = tmp_path / "local"
        root.mkdir()
        assert su.cmd_apply(root) == 2

    def test_remote_unreachable_exit_3(self, tmp_path, monkeypatch):
        root = make_local(tmp_path)
        monkeypatch.setenv("ZIPEC_VERSION_URLS", "file:///nonexistent/VERSION")
        assert su.cmd_apply(root) == 3
        assert su.cmd_check(root) == 3  # 无缓存且远端不可达
        assert (root / "VERSION").read_text().strip() == "3.5.0"


class TestApplySigning:
    """--apply 的签名信任锚与双源交叉验证。"""

    def _untouched(self, root):
        assert (root / "VERSION").read_text().strip() == "3.5.0"
        assert (root / "scripts" / "cast_chart.py").read_text() == "# old\n"
        assert (root / "stale_legacy.py").exists()
        assert not (root / "scripts" / "new_feature.py").exists()
        assert not (root / "manifest.json.sig").exists()

    def test_sig_fetched_separately_when_not_in_zip(self, tmp_path, monkeypatch):
        """zip 内无 sig、但源直链有：单独拉取并验签通过。"""
        root = make_local(tmp_path)
        vf, zp, dirs = make_remote(tmp_path, files=REMOTE_FILES, zip_sig=False)
        point_at_remote(monkeypatch, vf, zp, dirs)
        assert su.cmd_apply(root) == 0
        assert (root / "VERSION").read_text().strip() == "3.6.0"

    def test_missing_sig_everywhere_aborts(self, tmp_path, monkeypatch, capsys):
        """zip 与源直链都没有 sig → 视同为旧版或被篡改，拒。"""
        root = make_local(tmp_path)
        vf, zp, dirs = make_remote(tmp_path, files=REMOTE_FILES, zip_sig=False)
        for d in dirs:
            (d / "manifest.json.sig").unlink()
        point_at_remote(monkeypatch, vf, zp, dirs)
        assert su.cmd_apply(root) == 3
        assert "未带" in capsys.readouterr().err
        self._untouched(root)

    def test_sig_message_mismatch_aborts(self, tmp_path, monkeypatch, capsys):
        """签名签的是别的内容（manifest 被换）→ 验签拒。"""
        root = make_local(tmp_path)
        vf, zp, dirs = make_remote(tmp_path, files=REMOTE_FILES,
                                   sig_message=b"forged manifest")
        point_at_remote(monkeypatch, vf, zp, dirs)
        assert su.cmd_apply(root) == 3
        assert "签名校验不符" in capsys.readouterr().err
        self._untouched(root)

    def test_wrong_signing_key_aborts(self, tmp_path, monkeypatch, capsys):
        root = make_local(tmp_path)
        vf, zp, dirs = make_remote(tmp_path, files=REMOTE_FILES,
                                   sign_seed=OTHER_SEED)
        point_at_remote(monkeypatch, vf, zp, dirs)
        assert su.cmd_apply(root) == 3
        assert "签名校验不符" in capsys.readouterr().err
        self._untouched(root)

    def test_manifest_one_byte_flip_aborts(self, tmp_path, monkeypatch, capsys):
        """manifest 改一字节（源直链同步改、签名照旧）→ 验签拒。"""
        root = make_local(tmp_path)
        vf, zp, dirs = make_remote(tmp_path, files=REMOTE_FILES)
        for d in dirs:  # 两源与 zip 保持一致地改，隔离出"验签"这一道
            m = d / "manifest.json"
            data = bytearray(m.read_bytes())
            data[20] ^= 0x01
            m.write_bytes(bytes(data))
        # zip 内 manifest 也同步改
        import zipfile as zf_mod
        extract = tmp_path / "repack"
        with zf_mod.ZipFile(zp) as z:
            z.extractall(extract)
        m = extract / "ZiPingEightChar-main" / "manifest.json"
        data = bytearray(m.read_bytes())
        data[20] ^= 0x01
        m.write_bytes(bytes(data))
        with zf_mod.ZipFile(zp, "w") as z:
            for f in sorted(extract.rglob("*")):
                z.write(f, f.relative_to(extract))
        point_at_remote(monkeypatch, vf, zp, dirs)
        assert su.cmd_apply(root) == 3
        assert "签名校验不符" in capsys.readouterr().err
        self._untouched(root)

    def test_divergent_sources_abort(self, tmp_path, monkeypatch, capsys):
        root = make_local(tmp_path)
        vf, zp, dirs = make_remote(tmp_path, files=REMOTE_FILES,
                                   diverge_source=True)
        point_at_remote(monkeypatch, vf, zp, dirs)
        assert su.cmd_apply(root) == 3
        assert "不一致" in capsys.readouterr().err
        self._untouched(root)

    def test_source_unreachable_aborts(self, tmp_path, monkeypatch, capsys):
        """交叉验证时一个源不可达 → 宁可中止。"""
        root = make_local(tmp_path)
        vf, zp, dirs = make_remote(tmp_path, files=REMOTE_FILES)
        monkeypatch.setenv("ZIPEC_VERSION_URLS", vf.as_uri())
        monkeypatch.setenv("ZIPEC_ZIPBALL_URLS", zp.as_uri())
        monkeypatch.setenv("ZIPEC_MANIFEST_URLS",
                           (dirs[0] / "manifest.json").as_uri()
                           + ",file:///nonexistent/manifest.json")
        assert su.cmd_apply(root) == 3
        assert "交叉验证" in capsys.readouterr().err
        self._untouched(root)


class TestCastChartIntegration:
    def test_notice_on_stderr_stdout_clean(self):
        """排盘成功后 stderr 出一行提示；stdout 命盘契约不受影响。"""
        root = su.repo_root()
        cache_path = root / "data" / ".update_check.json"
        old_bytes = cache_path.read_bytes() if cache_path.exists() else None
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "checked_at": time.time(), "local_version": "3.5.0",
            "remote_version": "9.9.9", "update_available": True,
        }), encoding="utf-8")
        try:
            r = subprocess.run(
                [sys.executable, str(root / "scripts" / "cast_chart.py"),
                 "--name", "测试", "--gender", "男",
                 "--birth", "1990-05-14 08:30", "--place", "四川省成都市"],
                capture_output=True, text=True, timeout=60,
            )
            assert r.returncode == 0
            assert r.stdout.startswith("# 命盘：测试")
            assert "技能有新版本 9.9.9" in r.stderr
            assert "--apply" in r.stderr
        finally:
            if old_bytes is None:
                cache_path.unlink(missing_ok=True)
            else:
                cache_path.write_bytes(old_bytes)


class TestFetchFallback:
    def test_curl_fallback_when_urllib_ssl_fails(self, tmp_path, monkeypatch):
        """urllib 证书校验失败时回退系统 curl（macOS 框架版 Python 场景）。"""
        import urllib.request

        def _boom(*a, **k):
            raise urllib.request.URLError("CERTIFICATE_VERIFY_FAILED")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)

        fake_curl = tmp_path / "curl"
        fake_curl.write_text("#!/bin/sh\ncat \"$3\" | sed 's|^file://||' | xargs cat\n",
                             encoding="utf-8")
        src = tmp_path / "VERSION"
        src.write_text("9.9.9\n", encoding="utf-8")
        fake_curl.write_text(f'#!/bin/sh\ncat "{src}"\n', encoding="utf-8")
        fake_curl.chmod(0o755)
        monkeypatch.setattr(su.shutil, "which", lambda name: str(fake_curl))

        assert su._fetch_text("https://example.invalid/VERSION") == "9.9.9\n"

    def test_no_curl_no_urllib_raises(self, monkeypatch):
        import urllib.request

        def _boom(*a, **k):
            raise urllib.request.URLError("SSL")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        monkeypatch.setattr(su.shutil, "which", lambda name: None)
        with pytest.raises(Exception):
            su._fetch_text("https://example.invalid/VERSION")
