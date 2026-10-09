"""命主档案（memory/）读写层：frontmatter、文件名主键、小节替换。

纯标准库（Python ≥ 3.10），无第三方依赖。
frontmatter 只认本技能写出的受限 YAML 子集：``key: value`` 标量行、
双引号字符串、``[a, b]`` 行内列表——不引入 pyyaml，避免副本依赖膨胀。

档案规范见 memory/README.md；schema 改动须同步该文件。
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

ENV_VAR = "ZIPING_MEMORY_ROOT"  # 覆盖档案根目录的环境变量（--memory-root 优先）

# frontmatter 字段次序（写出固定；解析不依赖次序）
FIELDS = ("name", "gender", "birth_clock", "birthplace", "true_solar_time",
          "pillars", "day_master", "created_at", "updated_at")

# 正文固定小节次序（新建骨架用；盘面每次建档刷新，其余保留）
SECTIONS = ("盘面", "主要关注方向", "归纳", "流年大事", "反馈与澄清")

FEEDBACK_TAGS = ("【已核实】", "【已证伪】", "【未核实】")


def resolve_root(arg: str | None, script_file: str) -> Path:
    """档案根目录：--memory-root 参数 > 环境变量 ZIPING_MEMORY_ROOT > 技能根 memory/。"""
    if arg:
        return Path(arg).expanduser().resolve()
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).expanduser().resolve()
    return Path(script_file).resolve().parents[1] / "memory"


def key_hash(birth_clock: str, birthplace: str, gender: str) -> str:
    """hash6 = sha1(出生钟表时间 + 出生地 + 性别) 前 6 位，区分同盘不同人。"""
    raw = f"{birth_clock.strip()}{birthplace.strip()}{gender.strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]


def archive_name(pillars: list[str], gender: str, hash6: str) -> str:
    return f"{''.join(pillars)}-{gender}-{hash6}.md"


# —— frontmatter 读写（受限 YAML 子集）——

def _q(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unq(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return s


def dump_frontmatter(meta: dict) -> str:
    lines = ["---"]
    for k in FIELDS:
        v = meta.get(k, "")
        if isinstance(v, (list, tuple)):
            lines.append(f"{k}: [{', '.join(_q(x) for x in v)}]")
        else:
            lines.append(f"{k}: {_q(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """返回 (meta, 正文)。无 frontmatter 时 meta 为空 dict、正文为全文。"""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict = {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
        m = re.match(r"^(\w+)\s*:\s*(.*)$", lines[i].rstrip("\n"))
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            meta[k] = [_unq(x) for x in inner.split(",")] if inner else []
        else:
            meta[k] = _unq(v)
    if end is None:
        return {}, text
    return meta, "".join(lines[end + 1:])


# —— 正文骨架与小节替换 ——

def skeleton(name: str, gender: str, chart_md: str) -> str:
    return (
        f"# 档案：{name}（{gender}）\n\n"
        f"## 盘面\n\n{chart_md.strip()}\n\n"
        "## 主要关注方向\n\n（未记录）\n\n"
        "## 归纳\n\n"
        "- 性格：未断\n"
        "- 身体：未断\n"
        "- 事业：未断\n"
        "- 感情：未断\n"
        "- 婚姻：未断\n\n"
        "## 流年大事\n\n（未记录）\n\n"
        "## 反馈与澄清\n\n（无）\n"
    )


def replace_section(body: str, heading: str, content: str) -> str:
    """把 `## {heading}` 小节内容替换为 content；小节不存在则插到首个固定小节之前。

    「盘面」内嵌的命盘 Markdown 自带 `## ` 级标题（四柱、大运……），
    故小节边界只认档案自身的固定小节（SECTIONS），不认任意 `## ` 行。
    """
    lines = body.splitlines()
    target = f"## {heading}"
    bounds = {f"## {s}" for s in SECTIONS} - {target}
    start = next((i for i, ln in enumerate(lines) if ln.strip() == target), None)
    if start is None:
        first = next((i for i, ln in enumerate(lines) if ln.strip() in bounds),
                     len(lines))
        block = [target, "", *content.strip().splitlines(), ""]
        return "\n".join(lines[:first] + [""] + block + lines[first:]).strip() + "\n"
    nxt = next((i for i in range(start + 1, len(lines))
                if lines[i].strip() in bounds), len(lines))
    block = [lines[start], "", *content.strip().splitlines(), ""]
    return "\n".join(lines[:start] + block + lines[nxt:]).strip() + "\n"


# —— 检索 ——

def _norm(s: str) -> str:
    """大小写/空白容错比较口径。"""
    return "".join(str(s).split()).casefold()


def iter_archives(root: Path):
    d = root / "archives"
    if not d.is_dir():
        return
    yield from sorted(d.glob("*.md"))


def matches(meta: dict, *, name=None, birth=None, place=None,
            gender=None, pillars=None) -> bool:
    if name is not None and _norm(meta.get("name", "")) != _norm(name):
        return False
    if birth is not None and _norm(meta.get("birth_clock", "")) != _norm(birth):
        return False
    if place is not None and _norm(meta.get("birthplace", "")) != _norm(place):
        return False
    if gender is not None and _norm(meta.get("gender", "")) != _norm(gender):
        return False
    if pillars is not None:
        have = meta.get("pillars", [])
        if isinstance(have, str):
            have = have.split()
        if [_norm(p) for p in have] != [_norm(p) for p in pillars.split()]:
            return False
    return True
