#!/usr/bin/env python3
"""规则条款检索 —— 按关键词查 rules/ 条款全文，模型按需取规则。

用法：
    python query_rules.py 从格 破格 [--limit 8] [--and]
    python query_rules.py --id R-运-32
    python query_rules.py --list

规则库（rules/[0-9]*.md）为单一事实源：启动时现解析条款索引，无缓存文件。
条款体例：`### R-运-32 标题` 起头，正文到下一个 `##`/`###` 标题或文件尾。

关键词空格分隔，中文按子串匹配（不分词）。默认排序：全部关键词都命中的
条款排前，部分命中按命中词数 + 相关度分排序（罕见词加权威力更大，
标题命中加权、正文命中位置靠前加权）；--and 只保留全部关键词都命中的条款。

退出码：0 检索完成；1 无命中条款；2 输入不可用；3 内部错误。
"""
import argparse
import math
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _runtime_guard  # noqa: F401  import 即检查：Python < 3.10 时中文报错退出（码 3）

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"
CLAUSE_RE = re.compile(r"^### (R-\S+)\s+(.+?)\s*$")
HEADING_RE = re.compile(r"^##+ ")


@dataclass
class Clause:
    rid: str      # 条款编号，如 R-运-32
    title: str    # 标题
    body: str     # 正文（不含头部行，尾部空行与 --- 分隔线已剥除）
    file: str     # 所属文件名
    line: int     # 头部行号（1 起）
    order: int    # 解析序，排序兜底


def load_index(rules_dir: Path = RULES_DIR) -> list[Clause]:
    clauses: list[Clause] = []
    for path in sorted(rules_dir.glob("[0-9]*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        starts = [(i, CLAUSE_RE.match(ln)) for i, ln in enumerate(lines)]
        heads = [(i, m) for i, m in starts if m]
        for k, (i, m) in enumerate(heads):
            end = len(lines)
            for j in range(i + 1, len(lines)):
                if HEADING_RE.match(lines[j]):
                    end = j
                    break
            body = lines[i + 1:end]
            while body and (not body[-1].strip() or body[-1].strip() == "---"):
                body.pop()
            clauses.append(Clause(rid=m.group(1), title=m.group(2),
                                  body="\n".join(body), file=path.name,
                                  line=i + 1, order=len(clauses)))
    return clauses


def score_clause(c: Clause, keywords: list[str],
                 idf: dict[str, float]) -> tuple[int, float]:
    """返回 (命中关键词数, 相关度分)；一个关键词未命中则 hits 少一。"""
    hits, total = 0, 0.0
    text = c.title + "\n" + c.body
    for kw in keywords:
        n_title, n_body = c.title.count(kw), c.body.count(kw)
        if n_title + n_body == 0:
            continue
        hits += 1
        pos = text.find(kw)
        total += idf[kw] * (5.0 * n_title + n_body + (1.0 - pos / len(text)))
    return hits, total


def search(clauses: list[Clause], keywords: list[str],
           strict_and: bool = False) -> list[Clause]:
    idf = {}
    for kw in keywords:
        df = sum(1 for c in clauses if kw in c.title or kw in c.body)
        idf[kw] = math.log(1 + len(clauses) / (1 + df))
    scored = []
    for c in clauses:
        hits, score = score_clause(c, keywords, idf)
        if hits == 0 or (strict_and and hits < len(keywords)):
            continue
        scored.append((hits, score, c))
    scored.sort(key=lambda t: (-t[0], -t[1], t[2].order))
    return [c for _, _, c in scored]


def print_clause(c: Clause) -> None:
    print(f"## {c.rid}　{c.title}")
    print(f"{c.file}:{c.line}")
    print()
    print(c.body)
    print()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="query_rules.py",
        description="规则条款检索：按关键词查 rules/ 条款全文（编号 R-XX-NN）",
    )
    ap.add_argument("keywords", nargs="*", help="检索关键词，空格分隔，子串匹配")
    ap.add_argument("--limit", type=int, default=8, help="最多输出条款数（默认 8，0 为不限）")
    ap.add_argument("--and", dest="strict_and", action="store_true",
                    help="严格 AND：只保留全部关键词都命中的条款")
    ap.add_argument("--id", default=None, help="按编号精确取单条，如 R-运-32")
    ap.add_argument("--list", action="store_true", help="列出全部条款标题")
    a = ap.parse_args(argv)

    keywords = [kw for kw in (kw.strip() for kw in a.keywords) if kw]
    if not keywords and a.id is None and not a.list:
        print("ERROR: 至少给一个关键词，或用 --id / --list。", file=sys.stderr)
        return 2

    try:
        clauses = load_index()
        if not clauses:
            print(f"ERROR: 未解析到任何条款（{RULES_DIR}）。", file=sys.stderr)
            return 3

        if a.list:
            print(f"# 全部条款（{len(clauses)} 条）")
            print()
            cur = None
            for c in clauses:
                if c.file != cur:
                    cur = c.file
                    print(f"## {cur}")
                print(f"- {c.rid}　{c.title}")
            return 0

        if a.id is not None:
            for c in clauses:
                if c.rid == a.id:
                    print_clause(c)
                    return 0
            print(f"无命中条款：{a.id}", file=sys.stderr)
            return 1

        hits = search(clauses, keywords, strict_and=a.strict_and)
        if not hits:
            print(f"无命中条款：{' '.join(keywords)}", file=sys.stderr)
            return 1
        shown = hits if a.limit <= 0 else hits[:a.limit]
        mode = "AND 全命中" if a.strict_and else "相关度"
        print(f"# 规则检索：{' '.join(keywords)}（{mode}，命中 {len(hits)} 条，示 {len(shown)} 条）")
        print()
        for c in shown:
            print_clause(c)
        return 0
    except Exception:
        print("ERROR: 检索内部错误。", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
