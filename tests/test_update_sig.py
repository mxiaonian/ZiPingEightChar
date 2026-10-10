"""ed25519（RFC 8032）纯 Python 实现与 manifest 签名工具的测试。

TEST 1/2/3 为 RFC 8032 §7.1 官方测试向量（空消息/1 字节/2 字节）。
"""
import base64
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import _update_sig as ed

# RFC 8032 §7.1：(SECRET KEY, PUBLIC KEY, MESSAGE, SIGNATURE)
RFC8032_VECTORS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
     "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


class TestRFC8032Vectors:
    @pytest.mark.parametrize("i", range(len(RFC8032_VECTORS)))
    def test_vector(self, i):
        seed, pk, msg, sig = (bytes.fromhex(x) for x in RFC8032_VECTORS[i])
        assert ed.publickey(seed) == pk          # 公钥推导
        assert ed.sign(seed, msg) == sig         # 确定性签名逐字节一致
        assert ed.verify(pk, msg, sig) is True   # 验签通过


class TestSignVerifyRoundtrip:
    def test_roundtrip_random_key(self):
        seed = os.urandom(32)
        msg = '{"version": "9.9.9", "files": {}}'.encode()
        assert ed.verify(ed.publickey(seed), msg, ed.sign(seed, msg)) is True

    def test_message_one_byte_flip_fails(self):
        seed = os.urandom(32)
        pk = ed.publickey(seed)
        msg = b'{"files": {"a.py": "abc"}}'
        sig = ed.sign(seed, msg)
        bad = bytearray(msg)
        bad[3] ^= 0x01
        assert ed.verify(pk, bytes(bad), sig) is False

    def test_wrong_public_key_fails(self):
        msg = b"manifest"
        sig = ed.sign(os.urandom(32), msg)
        assert ed.verify(ed.publickey(os.urandom(32)), msg, sig) is False

    def test_forged_signature_fails(self):
        seed = os.urandom(32)
        pk, msg = ed.publickey(seed), b"manifest"
        sig = bytearray(ed.sign(seed, msg))
        sig[10] ^= 0x01  # 伪造：改 R 的一个字节
        assert ed.verify(pk, msg, bytes(sig)) is False
        assert ed.verify(pk, msg, os.urandom(64)) is False  # 全随机签名

    def test_malformed_inputs_return_false_not_raise(self):
        pk = ed.publickey(os.urandom(32))
        assert ed.verify(pk, b"m", b"") is False                # 长度不足
        assert ed.verify(pk, b"m", b"\xff" * 64) is False       # S 越界
        assert ed.verify(b"\xff" * 32, b"m", ed.sign(os.urandom(32), b"m")) is False
        assert ed.verify(b"short", b"m", b"x" * 64) is False    # 公钥长度错
        sig = bytearray(ed.sign(os.urandom(32), b"m"))
        sig[31] |= 0x80  # R 的 y 坐标 >= 2^255-19 界外/非法点
        sig[0:32] = b"\xff" * 32
        assert ed.verify(pk, b"m", bytes(sig)) is False


SIGN_TOOL = ROOT.parent / "tools" / "sign_manifest.py"


class TestSignManifestTool:
    def _repo(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "manifest.json").write_text(
            json.dumps({"version": "9.9.9", "files": {"a.py": "0" * 64}},
                       indent=2) + "\n", encoding="utf-8")
        seed = os.urandom(32)
        key = tmp_path / "signing.key"
        key.write_text("# 测试私钥\n# 生成日期：2026-10-10\n" + seed.hex() + "\n",
                       encoding="utf-8")
        return root, key, seed

    def test_sign_and_verify(self, tmp_path):
        root, key, seed = self._repo(tmp_path)
        r = subprocess.run(
            [sys.executable, str(SIGN_TOOL), "--repo-root", str(root),
             "--key", str(key)],
            capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        sig_text = (root / "manifest.json.sig").read_text(encoding="utf-8")
        assert sig_text.strip() == sig_text.rstrip("\n") and "\n" not in sig_text.strip()
        sig = base64.b64decode(sig_text.strip(), validate=True)
        assert len(sig) == 64
        manifest_bytes = (root / "manifest.json").read_bytes()
        assert ed.verify(ed.publickey(seed), manifest_bytes, sig) is True
        # manifest 改一字节 → 该签名不再有效
        bad = bytearray(manifest_bytes)
        bad[10] ^= 0x01
        assert ed.verify(ed.publickey(seed), bytes(bad), sig) is False

    def test_missing_manifest_exit_2(self, tmp_path):
        root, key, _ = self._repo(tmp_path)
        (root / "manifest.json").unlink()
        r = subprocess.run(
            [sys.executable, str(SIGN_TOOL), "--repo-root", str(root),
             "--key", str(key)],
            capture_output=True, text=True, timeout=60)
        assert r.returncode == 2
        assert "manifest.json" in r.stderr


class TestRealKeySetup:
    """作者侧私钥落盘状态：存在、权限 600、绝不进 git 仓库。"""

    def test_key_file_perms_and_not_in_repo(self):
        key = Path.home() / ".zipec" / "signing.key"
        if not key.exists():
            pytest.skip("作者机上才有私钥")
        assert stat.S_IMODE(key.stat().st_mode) == 0o600
        assert stat.S_IMODE(key.parent.stat().st_mode) == 0o700
        r = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                           capture_output=True, text=True)
        assert "signing.key" not in r.stdout
        # 私钥对应的公钥 == self_update 内置信任锚
        import self_update as su
        seed = bytes.fromhex(
            [ln for ln in key.read_text().splitlines()
             if ln.strip() and not ln.startswith("#")][0])
        assert ed.publickey(seed).hex() == su.UPDATE_PUBLIC_KEY_HEX
        assert ed.fingerprint(ed.publickey(seed)) == (
            "3089bc1cc9a453e5be66a36574635da6b2ad9797c57af11164111faca157411c")
