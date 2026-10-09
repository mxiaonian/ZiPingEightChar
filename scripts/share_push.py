#!/usr/bin/env python3
"""脱敏包推送 —— 把 share/pending/ 的包 git commit+push 到共建远端。

用法：python share_push.py [--root 技能根目录]

远端取自 share/config.json 的 github_remote / gitea_remote（占位为空则跳过，
由授权方填写；亦可用环境变量 ZIPING_SHARE_GITHUB_REMOTE /
ZIPING_SHARE_GITEA_REMOTE 覆盖）。两个远端逐个尝试，至少一个成功即算成功。

推送成功后：调 _license_gate.grant_uses(root, 10, 盘hash) 计励（同一盘只计一次），
并把该包移入 share/pushed/。推送失败保留 pending，退出码 3。
无 git 或无网络安静失败（不打栈）。

退出码：0 至少一包推送成功或无包可推；2 输入不可用；3 推送失败。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _license_gate as gate

GRANT_USES = 10  # 每盘推送成功的计励次数
ENV_GITHUB = "ZIPING_SHARE_GITHUB_REMOTE"
ENV_GITEA = "ZIPING_SHARE_GITEA_REMOTE"
_GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "true"}


def _git(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env=_GIT_ENV,
                          capture_output=True, text=True, timeout=60)


def _push_to_remote(remote: str, pkg: Path, workdir: str) -> bool:
    """克隆远端 → 放入脱敏包 → commit+push。任一步失败返回 False（安静）。"""
    try:
        if _git("clone", "--depth", "50", remote, workdir).returncode != 0:
            return False
        dst = Path(workdir) / pkg.name
        shutil.copy2(pkg, dst)
        if _git("add", pkg.name, cwd=workdir).returncode != 0:
            return False
        commit = _git("-c", "user.name=ziping-share",
                      "-c", "user.email=ziping-share@localhost",
                      "commit", "--allow-empty", "-m", f"share: {pkg.stem}",
                      cwd=workdir)
        if commit.returncode != 0:
            return False
        return _git("push", "origin", "HEAD:main", cwd=workdir).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _remotes(root: Path) -> list[tuple[str, str]]:
    cfg = {}
    cfg_path = root / "share" / "config.json"
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cfg = {}
    out = []
    for key, env in (("github_remote", ENV_GITHUB), ("gitea_remote", ENV_GITEA)):
        val = os.environ.get(env) or str(cfg.get(key) or "").strip()
        if val:
            out.append((key, val))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(prog="share_push.py",
                                 description="把 share/pending/ 的脱敏包推送到共建远端，"
                                 "成功后计励 +10 次并移入 share/pushed/")
    ap.add_argument("--root", default=None,
                    help="技能根目录（默认取脚本所在技能根，测试覆盖用）")
    a = ap.parse_args()
    root = (Path(a.root).expanduser().resolve() if a.root
            else Path(__file__).resolve().parents[1])

    if shutil.which("git") is None:
        print("ERROR: 未找到 git，无法推送；pending 保留。", file=sys.stderr)
        return 3
    remotes = _remotes(root)
    if not remotes:
        print("ERROR: share/config.json 未配置远端（github_remote/gitea_remote "
              "由授权方填写）；pending 保留。", file=sys.stderr)
        return 3

    pending = root / "share" / "pending"
    pushed = root / "share" / "pushed"
    packages = sorted(pending.glob("*.json")) if pending.is_dir() else []
    if not packages:
        print("share/pending/ 无待推送脱敏包。")
        return 0

    pushed.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    for pkg in packages:
        chart_hash = pkg.stem
        ok_remotes = []
        for name, remote in remotes:
            with tempfile.TemporaryDirectory(prefix="ziping-share-") as td:
                if _push_to_remote(remote, pkg, td):
                    ok_remotes.append(name)
        if not ok_remotes:
            print(f"FAIL {pkg.name}：所有远端推送失败（无网络或远端不可达），"
                  f"pending 保留。", file=sys.stderr)
            continue
        granted = gate.grant_uses(root, GRANT_USES, chart_hash)
        shutil.move(str(pkg), str(pushed / pkg.name))
        note = (f"+{GRANT_USES} 次（新增计励）" if granted
                else "该盘已计励过，本次不重复加次")
        print(f"OK {pkg.name} → {'、'.join(ok_remotes)}；{note}")
        n_ok += 1

    return 0 if n_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
