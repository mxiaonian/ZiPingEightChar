#!/usr/bin/env python3
"""技能自更新：版本检查、异步提示、应用更新。

用法：
    python scripts/self_update.py --check    检查更新（24 小时缓存，重复检查不拉网络）
    python scripts/self_update.py --notify   只读缓存打印提示，绝不碰网络（供 cast_chart 调用）
    python scripts/self_update.py --apply    下载 zipball → 按 manifest 逐文件校验 → 同步本地

退出码（--apply）：0 成功；2 无需更新或配置缺失；3 失败（本地原样不动）。

远端双线路 failover：GitHub 优先，Gitea 兜底。HTTPS_PROXY/HTTP_PROXY 等
代理环境变量由 urllib 默认读取、自动生效。测试或自建场景可用环境变量
ZIPEC_VERSION_URLS / ZIPEC_ZIPBALL_URLS（逗号分隔）整体覆盖远端地址，
支持 file:// 形式。
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

# ---- 远端配置（GitHub 优先，Gitea 兜底）----
GITHUB_VERSION_URL = "https://raw.githubusercontent.com/mxiaonian/ZiPingEightChar/main/VERSION"
GITHUB_ZIPBALL_URL = "https://codeload.github.com/mxiaonian/ZiPingEightChar/zip/refs/heads/main"
GITEA_VERSION_URL = "https://git.lingyaomiaojie.com/moxiaonian/ZiPingEightChar/raw/branch/main/VERSION"
GITEA_ZIPBALL_URL = "https://git.lingyaomiaojie.com/moxiaonian/ZiPingEightChar/archive/main.zip"

CACHE_REL = "data/.update_check.json"
CACHE_TTL_SECONDS = 24 * 3600
NETWORK_TIMEOUT = 3

# 更新管辖区之外：同步时绝不覆盖、绝不删除（与 tools/build_manifest.py 排除表一致）
PRESERVE_FILES = {"data/.license.json", "data/.update_check.json"}
PRESERVE_DIRS = {".git", "memory/archives", "share/pending", "share/pushed"}
PRESERVE_DIR_NAMES = {".git", "__pycache__", ".pytest_cache"}
PRESERVE_FILE_NAMES = {".DS_Store"}
PRESERVE_SUFFIXES = {".pyc"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _version_urls() -> list:
    env = os.environ.get("ZIPEC_VERSION_URLS")
    if env:
        return [u.strip() for u in env.split(",") if u.strip()]
    return [GITHUB_VERSION_URL, GITEA_VERSION_URL]


def _zipball_urls() -> list:
    env = os.environ.get("ZIPEC_ZIPBALL_URLS")
    if env:
        return [u.strip() for u in env.split(",") if u.strip()]
    return [GITHUB_ZIPBALL_URL, GITEA_ZIPBALL_URL]


def _fetch_text(url: str, timeout: int = NETWORK_TIMEOUT) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")


def _download(url: str, dest: Path, timeout: int = NETWORK_TIMEOUT) -> None:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        with open(dest, "wb") as fh:
            shutil.copyfileobj(r, fh)


def parse_version(text: str) -> tuple:
    parts = text.strip().split(".")
    if not parts or any(not p.isdigit() for p in parts):
        raise ValueError(f"无法解析版本号: {text!r}")
    return tuple(int(p) for p in parts)


def read_local_version(root: Path):
    try:
        return (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- 缓存（data/.update_check.json）----

def load_cache(root: Path):
    try:
        return json.loads((root / CACHE_REL).read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cache(root: Path, remote_version, local_version) -> dict:
    update_available = False
    if remote_version and local_version:
        try:
            update_available = parse_version(remote_version) > parse_version(local_version)
        except ValueError:
            update_available = False
    cache = {
        "checked_at": time.time(),
        "checked_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "local_version": local_version,
        "remote_version": remote_version,
        "update_available": update_available,
    }
    p = root / CACHE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cache


def _cache_fresh(cache) -> bool:
    try:
        return time.time() - float(cache.get("checked_at", 0)) < CACHE_TTL_SECONDS
    except Exception:
        return False


def cache_stale(root: Path) -> bool:
    cache = load_cache(root)
    return not _cache_fresh(cache)


def _fetch_remote_version():
    """双线 failover：按序尝试各源，返回第一个成功的 VERSION 文本；全失败返回 None。"""
    for url in _version_urls():
        try:
            text = _fetch_text(url).strip()
            if text:
                return text
        except Exception:
            continue
    return None


# ---- --check / --notify ----

def _print_check_result(cache, note: str = "") -> None:
    if cache.get("update_available") and cache.get("remote_version"):
        print(f"有新版本 {cache['remote_version']}（当前 {cache.get('local_version') or '?'}）{note}")
    else:
        print(f"已是最新（{cache.get('local_version') or cache.get('remote_version') or '?'}）{note}")


def cmd_check(root: Path, force: bool = False) -> int:
    cache = load_cache(root)
    if not force and _cache_fresh(cache):
        _print_check_result(cache, note="（24 小时内已检查过）")
        return 0
    remote = _fetch_remote_version()
    if remote is None:
        if cache:
            _print_check_result(cache, note="（网络不可达，沿用上次结果）")
            return 0
        print("检查失败：远端 VERSION 不可达", file=sys.stderr)
        return 3
    _print_check_result(_write_cache(root, remote, read_local_version(root)))
    return 0


def notify_message(root: Path):
    """只读缓存、绝不碰网络：有可更新版本时返回一行提示，否则返回 None。"""
    cache = load_cache(root)
    if not cache or not cache.get("update_available"):
        return None
    ver = cache.get("remote_version") or "?"
    return f"技能有新版本 {ver}，运行 `python scripts/self_update.py --apply` 可更新"


def cmd_notify(root: Path) -> int:
    msg = notify_message(root)
    if msg:
        print(msg, file=sys.stderr)
    return 0


def refresh_cache(root: Path) -> None:
    """同步刷新缓存；任何失败都静默（供后台线程调用）。"""
    try:
        remote = _fetch_remote_version()
        if remote is not None:
            _write_cache(root, remote, read_local_version(root))
    except Exception:
        pass


def refresh_cache_async(root: Path) -> None:
    """缓存过期（>24h）才起后台线程拉一次远端 VERSION；主流程不等它。"""
    try:
        if not cache_stale(root):
            return
        threading.Thread(target=refresh_cache, args=(root,), daemon=True).start()
    except Exception:
        pass


# ---- --apply ----

def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def _preserved_dir(root: Path, d: Path) -> bool:
    if d.name in PRESERVE_DIR_NAMES:
        return True
    rel = _rel(root, d)
    return any(rel == ex or rel.startswith(ex + "/") for ex in PRESERVE_DIRS)


def _preserved_file(root: Path, f: Path) -> bool:
    rel = _rel(root, f)
    if rel in PRESERVE_FILES or f.name in PRESERVE_FILE_NAMES:
        return True
    if f.suffix in PRESERVE_SUFFIXES:
        return True
    # 位于保留目录（或其子目录）内的文件一律保留
    parts = rel.split("/")[:-1]
    for i, name in enumerate(parts):
        if name in PRESERVE_DIR_NAMES or "/".join(parts[: i + 1]) in PRESERVE_DIRS:
            return True
    return False


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest_real = os.path.realpath(dest)
    for info in zf.infolist():
        target = os.path.realpath(dest / info.filename)
        if target != dest_real and not target.startswith(dest_real + os.sep):
            raise ValueError(f"zip 内含越界路径: {info.filename!r}")
    zf.extractall(dest)


def _find_source_root(extract_dir: Path):
    """zipball 通常带一层顶层目录（GitHub: <repo>-main/；Gitea: <repo>/）。"""
    if (extract_dir / "manifest.json").is_file():
        return extract_dir
    hits = [d for d in sorted(extract_dir.iterdir())
            if d.is_dir() and (d / "manifest.json").is_file()]
    return hits[0] if len(hits) == 1 else None


def _verify_manifest(src: Path, files: dict):
    """逐文件校验 sha256；返回错误信息列表（空 = 全部通过）。只校验，不动本地。"""
    errors = []
    for rel, want in files.items():
        f = src / rel
        if not f.is_file():
            errors.append(f"缺失 {rel}")
        elif _sha256(f) != want:
            errors.append(f"校验不符 {rel}")
    return errors


def _sync(root: Path, src: Path, files: dict) -> None:
    managed = set(files) | {"manifest.json", "VERSION"}
    copied = deleted = 0
    for rel in sorted(managed - {"VERSION"}):  # VERSION 最后写
        s = src / rel
        if not s.is_file():
            continue
        d = root / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        copied += 1
    # 删除本地多余但清单不含的文件（仅清单管辖区；保留区一律不动）
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        d = Path(dirpath)
        for name in filenames:
            f = d / name
            if _preserved_file(root, f) or _rel(root, f) in managed:
                continue
            f.unlink()
            deleted += 1
        if d != root and not _preserved_dir(root, d) and not any(d.iterdir()):
            d.rmdir()
    # 最后写 VERSION
    if (src / "VERSION").is_file():
        shutil.copy2(src / "VERSION", root / "VERSION")
    print(f"同步完成：写入 {copied} 个文件，清理 {deleted} 个多余文件")


def cmd_apply(root: Path) -> int:
    local = read_local_version(root)
    if local is None:
        print("配置缺失：本地没有 VERSION 文件", file=sys.stderr)
        return 2
    print(f"本地版本 {local}，正在获取远端版本…")
    remote = _fetch_remote_version()
    if remote is None:
        print("失败：远端 VERSION 不可达（本地未改动）", file=sys.stderr)
        return 3
    print(f"远端版本 {remote}")
    try:
        if parse_version(remote) <= parse_version(local):
            print("已是最新，无需更新")
            return 2
    except ValueError as e:
        print(f"失败：{e}（本地未改动）", file=sys.stderr)
        return 3

    with tempfile.TemporaryDirectory(prefix="zipec-update-") as td:
        zip_path = Path(td) / "remote.zip"
        ok = False
        for url in _zipball_urls():
            try:
                print(f"下载 {url} …")
                _download(url, zip_path)
                ok = True
                break
            except Exception as e:
                print(f"  下载失败（{e}），尝试下一源")
        if not ok:
            print("失败：所有更新源均不可达（本地未改动）", file=sys.stderr)
            return 3

        try:
            extract_dir = Path(td) / "src"
            extract_dir.mkdir()
            with zipfile.ZipFile(zip_path) as zf:
                _safe_extract(zf, extract_dir)
        except Exception as e:
            print(f"失败：zip 解压异常（{e}）（本地未改动）", file=sys.stderr)
            return 3

        src = _find_source_root(extract_dir)
        if src is None:
            print("失败：远端包内找不到 manifest.json（本地未改动）", file=sys.stderr)
            return 3
        try:
            manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
            files = manifest["files"]
        except Exception as e:
            print(f"失败：manifest.json 无法解析（{e}）（本地未改动）", file=sys.stderr)
            return 3

        errors = _verify_manifest(src, files)
        if errors:
            print(f"失败：{len(errors)} 个文件与清单不符，已中止（本地未改动）",
                  file=sys.stderr)
            for e in errors[:5]:
                print(f"  {e}", file=sys.stderr)
            return 3
        print(f"清单校验通过（{len(files)} 个文件），开始同步…")
        _sync(root, src, files)

    try:
        _write_cache(root, remote, remote)
    except Exception:
        pass
    print(f"更新完成：{local} → {remote}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="self_update.py", description="技能自更新")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="检查更新（24 小时缓存）")
    g.add_argument("--notify", action="store_true", help="只读缓存打印提示，不碰网络")
    g.add_argument("--apply", action="store_true", help="校验并应用更新")
    a = ap.parse_args()
    root = repo_root()
    if a.check:
        return cmd_check(root)
    if a.notify:
        return cmd_notify(root)
    return cmd_apply(root)


if __name__ == "__main__":
    raise SystemExit(main())
