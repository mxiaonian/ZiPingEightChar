"""外层 tools/sync_license_copy.py 的集成测试。

sync/build/sign 工具留在授权方工作区外层 tools/，不随本仓库分发；
副本或 clone 环境下 tools/ 不存在，整个模块 skip。

测试用微型假母版（monkeypatch 替换模块 SRC）同步进临时授权副本，
不碰真实母版与真实副本；签名用测试私钥，UPDATE_PUBLIC_KEY_HEX 同步造假。
"""
import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT.parent / "tools"
SYNC_TOOL = TOOLS / "sync_license_copy.py"

pytestmark = pytest.mark.skipif(
    not (SYNC_TOOL.is_file()
         and (TOOLS / "build_manifest.py").is_file()
         and (TOOLS / "sign_manifest.py").is_file()),
    reason="外层 tools/ 不随仓库分发，本环境无同步工具",
)

sys.path.insert(0, str(ROOT / "scripts"))
import _update_sig  # noqa: E402

TEST_SEED = bytes(range(32))
TEST_PK_HEX = _update_sig.publickey(TEST_SEED).hex()
OTHER_SEED = bytes(range(32, 64))  # 与内置公钥不匹配的错误私钥
STALE_SIG = base64.b64encode(b"\x00" * 64).decode("ascii") + "\n"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sync_tool = _load_module("sync_license_copy", SYNC_TOOL)
build_manifest = _load_module("build_manifest", TOOLS / "build_manifest.py")


def _make_master(src: Path, pk_hex: str) -> None:
    """微型母版：VERSION/SKILL.md/rules×2/cast_chart.py/self_update.py + 过期 manifest。"""
    (src / "rules").mkdir(parents=True)
    (src / "scripts").mkdir(parents=True)
    (src / "VERSION").write_text("9.9.9-test\n", encoding="utf-8")
    (src / "SKILL.md").write_text("---\nname: test\n---\n\n# 母版\n",
                                  encoding="utf-8")
    (src / "rules" / "r1.md").write_text("# 规则一\n", encoding="utf-8")
    (src / "rules" / "r2.md").write_text("# 规则二\n", encoding="utf-8")
    (src / "scripts" / "cast_chart.py").write_text(
        "#!/usr/bin/env python3\nprint('chart')\n", encoding="utf-8")
    (src / "scripts" / "self_update.py").write_text(
        f'UPDATE_PUBLIC_KEY_HEX = "{pk_hex}"\n', encoding="utf-8")
    # 母版随仓库分发的旧 manifest/sig：同步进副本后必须被重建/重签或移除
    (src / "manifest.json").write_text('{"version": "9.9.9-test", "files": {}}\n',
                                       encoding="utf-8")
    (src / "manifest.json.sig").write_text(STALE_SIG, encoding="utf-8")


def _make_copy(dst: Path) -> None:
    """已存在的授权副本：授权状态文件 + 带副本编号水印的 SKILL.md。"""
    (dst / "data").mkdir(parents=True)
    (dst / "data" / ".license.json").write_text("{}", encoding="utf-8")
    (dst / "SKILL.md").write_text(
        "---\nname: test\n---\n\n<!-- 副本编号：LY-TEST0000-0000 · 授权对象：测试员 · "
        "测试授权 · 禁止商业用途与个人传播 -->\n", encoding="utf-8")


@pytest.fixture
def pair(tmp_path, monkeypatch):
    src, dst = tmp_path / "master", tmp_path / "copy"
    _make_master(src, TEST_PK_HEX)
    _make_copy(dst)
    monkeypatch.setattr(sync_tool, "SRC", src)
    return src, dst


def _key_file(tmp_path, seed: bytes) -> Path:
    p = tmp_path / "signing.key"
    p.write_text("# 测试私钥\n" + seed.hex() + "\n", encoding="utf-8")
    return p


def _manifest_on_disk(dst: Path) -> dict:
    return json.loads((dst / "manifest.json").read_text(encoding="utf-8"))


def test_sync_rebuilds_manifest_and_signs(pair, tmp_path, capsys):
    """同步后 manifest 与水印后文件逐哈希一致，sig 用内置公钥验签通过。"""
    _src, dst = pair
    key = _key_file(tmp_path, TEST_SEED)
    assert sync_tool.main(["--key", str(key), str(dst)]) == 0

    manifest = _manifest_on_disk(dst)
    # 与 build_manifest 对水印后磁盘文件重新计算的结果完全一致
    assert manifest == build_manifest.build_manifest(dst)
    for rel in ("SKILL.md", "rules/r1.md", "rules/r2.md", "scripts/cast_chart.py"):
        assert rel in manifest["files"]
    # 水印确实落在文件里（哈希对应的是水印后内容）
    assert "LY-TEST0000-0000" in (dst / "SKILL.md").read_text(encoding="utf-8")

    sig_text = (dst / "manifest.json.sig").read_text(encoding="utf-8")
    assert sig_text != STALE_SIG  # 过期 sig 被新签名覆盖而非原样保留
    sig = base64.b64decode(sig_text.strip(), validate=True)
    assert _update_sig.verify(bytes.fromhex(TEST_PK_HEX),
                              (dst / "manifest.json").read_bytes(), sig)
    out = capsys.readouterr().out
    assert f"公钥指纹 {_update_sig.fingerprint(bytes.fromhex(TEST_PK_HEX))[:16]}" in out
    assert f"{len(manifest['files'])} 个文件" in out


def test_sync_no_sign_removes_stale_sig(pair, capsys):
    """--no-sign：manifest 重建、过期 sig 移除、WARN、退出码 0。"""
    _src, dst = pair
    assert sync_tool.main(["--no-sign", str(dst)]) == 0
    assert _manifest_on_disk(dst) == build_manifest.build_manifest(dst)
    assert not (dst / "manifest.json.sig").exists()
    assert "WARN" in capsys.readouterr().err


def test_sync_missing_key_fails_closed(pair, tmp_path, capsys):
    """私钥缺失：manifest 已重建、过期 sig 移除、报错、退出码非 0。"""
    _src, dst = pair
    missing = tmp_path / "no-such.key"
    assert sync_tool.main(["--key", str(missing), str(dst)]) == 1
    assert _manifest_on_disk(dst) == build_manifest.build_manifest(dst)
    assert not (dst / "manifest.json.sig").exists()
    err = capsys.readouterr().err
    assert "私钥不存在" in err and "未签名" in err


def test_sync_wrong_key_fails_closed(pair, tmp_path, capsys):
    """签名私钥与副本内置公钥不匹配：独立验签拦截，sig 移除，退出码非 0。"""
    _src, dst = pair
    key = _key_file(tmp_path, OTHER_SEED)
    assert sync_tool.main(["--key", str(key), str(dst)]) == 1
    assert _manifest_on_disk(dst) == build_manifest.build_manifest(dst)
    assert not (dst / "manifest.json.sig").exists()
    assert "验签" in capsys.readouterr().err
