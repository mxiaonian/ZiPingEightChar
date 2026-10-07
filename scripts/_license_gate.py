"""软授权锁（防君子不防小人）。

总开关就是下面的 `_ENABLED` 一行变量：置 False 则完全放行。
本锁只是授权边界的可见表达，真正的约束在 LICENSE.md 的法律条款——
绕过、篡改、移除软锁或水印，即构成对授权的违反。

母版（技能开发目录）无 `data/.license.json`，本模块全部放行；
由 `tools/make_license_copy.py` 生成的定制副本带该状态文件，
按剩余次数与到期日限制使用，并以签名防止手工篡改状态文件。

退出码 4 = 授权不可用（次数用尽 / 已过期 / 状态文件被篡改）。
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

_ENABLED = True  # 软锁总开关：False = 完全放行

_SALT = "lingyao-miaojie-ziping-eightchar"
_COMPANY = "四川灵爻妙解文化传播有限公司"
STATE_REL = Path("data") / ".license.json"


def _state_path(root: Path) -> Path:
    return root / STATE_REL


def _sig(st: dict) -> str:
    raw = "|".join([
        str(st["copy_id"]), str(st["licensee"]), str(st["max_uses"]),
        str(st["remaining_uses"]), str(st["expires_at"]), _SALT,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _load(root: Path) -> dict | None:
    p = _state_path(root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # 状态文件损坏按篡改变体处理：拒跑
        return {"copy_id": "?", "licensee": "?", "remaining_uses": 0,
                "max_uses": 0, "expires_at": None, "sig": ""}


def _deny(reason: str, st: dict) -> str:
    return (f"授权不可用：{reason}。"
            f"（副本编号 {st.get('copy_id', '?')}，授权对象：{st.get('licensee', '?')}）"
            f"本技能为测试授权副本，禁止商业用途与个人传播；"
            f"如需续期或正式授权，请联系{_COMPANY}。")


def check(root: Path) -> str | None:
    """返回 None 表示放行；返回字符串表示拒跑原因（由调用方打印到 stderr，退出码 4）。"""
    if not _ENABLED:
        return None
    st = _load(root)
    if st is None:
        return None  # 母版无状态文件，不锁
    if st.get("sig") != _sig(st):
        return _deny("授权状态校验失败（授权文件被改动过）", st)
    exp = st.get("expires_at")
    if exp and date.today() > date.fromisoformat(exp):
        return _deny(f"授权已于 {exp} 到期", st)
    if st.get("remaining_uses", 0) <= 0:
        return _deny("本副本的使用次数已用尽", st)
    return None


def consume(root: Path) -> None:
    """成功排盘一次后扣减一次。仅在 check 放行后调用。"""
    if not _ENABLED:
        return
    st = _load(root)
    if st is None:
        return
    st["remaining_uses"] = max(0, int(st.get("remaining_uses", 0)) - 1)
    st["sig"] = _sig(st)
    _state_path(root).write_text(
        json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def write_state(root: Path, *, copy_id: str, licensee: str,
                max_uses: int, expires_at: str | None = None) -> dict:
    """生成授权状态文件（供 tools/make_license_copy.py 调用，签名算法单点在此）。"""
    st = {
        "copy_id": copy_id,
        "licensee": licensee,
        "issued_at": date.today().isoformat(),
        "expires_at": expires_at,
        "max_uses": max_uses,
        "remaining_uses": max_uses,
    }
    st["sig"] = _sig(st)
    p = _state_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    return st
