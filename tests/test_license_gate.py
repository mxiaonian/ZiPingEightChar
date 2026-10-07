"""软授权锁：母版放行、副本扣次、用尽/过期/篡改/总开关。"""
import json
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
