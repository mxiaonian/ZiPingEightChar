"""软授权锁：母版放行、副本扣次、用尽/过期/篡改/总开关、公众版首启签发、计励幂等。"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import _license_gate as gate


@pytest.fixture
def root(tmp_path):
    return tmp_path


def make_state(root, **kw):
    kw.setdefault("copy_id", "LY-20261007-A3F9")
    kw.setdefault("licensee", "张三")
    kw.setdefault("max_uses", 2)
    return gate.write_state(root, **kw)


class TestMasterCopy:
    def test_no_state_file_passes(self, root):
        assert gate.check(root) is None

    def test_consume_without_state_is_noop(self, root):
        gate.consume(root)
        assert not (root / "data" / ".license.json").exists()


class TestLicensedCopy:
    def test_decrements_per_use_then_denies(self, root):
        make_state(root)
        assert gate.check(root) is None
        gate.consume(root)
        st = json.loads((root / "data" / ".license.json").read_text("utf-8"))
        assert st["remaining_uses"] == 1
        assert gate.check(root) is None
        gate.consume(root)
        assert "次数已用尽" in gate.check(root)

    def test_expired_denies(self, root):
        make_state(root, expires_at="2020-01-01")
        assert "到期" in gate.check(root)

    def test_future_expiry_passes(self, root):
        make_state(root, expires_at="2999-01-01")
        assert gate.check(root) is None

    def test_tampered_state_denies(self, root):
        make_state(root)
        p = root / "data" / ".license.json"
        st = json.loads(p.read_text("utf-8"))
        st["remaining_uses"] = 999  # 手改次数但不重算签名
        p.write_text(json.dumps(st, ensure_ascii=False), "utf-8")
        assert "校验失败" in gate.check(root)

    def test_corrupted_state_denies(self, root):
        (root / "data").mkdir()
        (root / "data" / ".license.json").write_text("not json", "utf-8")
        assert gate.check(root) is not None


class TestMasterSwitch:
    def test_disabled_gate_passes_exhausted_copy(self, root, monkeypatch):
        make_state(root, max_uses=0)
        monkeypatch.setattr(gate, "_ENABLED", False)
        assert gate.check(root) is None
        gate.consume(root)  # 不扣次
        st = json.loads((root / "data" / ".license.json").read_text("utf-8"))
        assert st["remaining_uses"] == 0


def make_public_marker(root):
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / ".public_edition.json").write_text(json.dumps(
        {"edition": "public", "pack_version": "0.1.0",
         "pool_copy_id": "LY-20261009-PUB0"}, ensure_ascii=False), "utf-8")


class TestPublicEdition:
    def test_first_check_issues_personal_license(self, root):
        make_public_marker(root)
        assert gate.check(root) is None
        st = json.loads((root / "data" / ".license.json").read_text("utf-8"))
        assert re.fullmatch(r"LY-\d{8}-[0-9A-F]{4}", st["copy_id"])
        assert st["licensee"] == "public-personal"
        assert st["max_uses"] == 20
        assert st["remaining_uses"] == 20
        assert st["expires_at"] is None
        assert st["granted_archives"] == []

    def test_second_check_keeps_same_copy_id(self, root):
        make_public_marker(root)
        gate.check(root)
        first = json.loads((root / "data" / ".license.json").read_text("utf-8"))
        gate.check(root)
        second = json.loads((root / "data" / ".license.json").read_text("utf-8"))
        assert first["copy_id"] == second["copy_id"]
        assert first["sig"] == second["sig"]

    def test_issued_copy_consumes_then_denies(self, root):
        make_public_marker(root)
        assert gate.check(root) is None
        for _ in range(20):
            gate.consume(root)
        assert "次数已用尽" in gate.check(root)

    def test_master_without_marker_stays_unlocked(self, root):
        assert gate.check(root) is None  # 母版：无状态文件也无标记
        assert not (root / "data" / ".license.json").exists()


class TestGrantUses:
    def test_grant_adds_uses_and_is_idempotent(self, root):
        make_state(root, max_uses=5)
        assert gate.grant_uses(root, 10, "hashA") is True
        st = json.loads((root / "data" / ".license.json").read_text("utf-8"))
        assert st["remaining_uses"] == 15
        # 同一盘只计一次：第二次返回 False 且不加次
        assert gate.grant_uses(root, 10, "hashA") is False
        st = json.loads((root / "data" / ".license.json").read_text("utf-8"))
        assert st["remaining_uses"] == 15
        assert st["granted_archives"] == ["hashA"]
        # 另一盘可再计
        assert gate.grant_uses(root, 10, "hashB") is True
        st = json.loads((root / "data" / ".license.json").read_text("utf-8"))
        assert st["remaining_uses"] == 25
        assert st["granted_archives"] == ["hashA", "hashB"]

    def test_grant_on_master_returns_true_without_state(self, root):
        assert gate.grant_uses(root, 10, "hashA") is True
        assert not (root / "data" / ".license.json").exists()

    def test_grant_on_tampered_state_refused(self, root):
        make_state(root, max_uses=5)
        p = root / "data" / ".license.json"
        st = json.loads(p.read_text("utf-8"))
        st["remaining_uses"] = 999  # 手改次数但不重算签名
        p.write_text(json.dumps(st, ensure_ascii=False), "utf-8")
        assert gate.grant_uses(root, 10, "hashA") is False
        st = json.loads(p.read_text("utf-8"))
        assert st["remaining_uses"] == 999  # 未被计励写回

    def test_state_written_by_old_schema_still_verifiable(self, root):
        # 旧格式状态文件（无 granted_archives 字段）签名校验不受影响
        st = {
            "copy_id": "LY-20261007-A3F9", "licensee": "张三",
            "issued_at": "2026-10-07", "expires_at": None,
            "max_uses": 2, "remaining_uses": 2,
        }
        st["sig"] = gate._sig(st)
        (root / "data").mkdir()
        (root / "data" / ".license.json").write_text(
            json.dumps(st, ensure_ascii=False), "utf-8")
        assert gate.check(root) is None
        assert gate.grant_uses(root, 10, "hashA") is True
        st = json.loads((root / "data" / ".license.json").read_text("utf-8"))
        assert st["remaining_uses"] == 12
        assert gate.check(root) is None
