#!/usr/bin/env python3
"""试题原始包 → questions/（盲版）+ answers/（答案键）分离生成器。

输入为含官方答案的赛事原始 JSON（contest8_*.json 结构：第 0 项元数据，
其后为命主数组，每命主 questions 列表，每题含 answer 字段）。输出：

- <out>/questions/<file>.json：与原版同构但剥离每题 answer 的盲版（求解端只准读这里）；
- <out>/answers/<file>.json：答案键，仅 [元数据, {person_id, answers: [
  {question_index, answer, dimension}, ...]} ...]；维度标签可由 --scores
  指向的官方跑分目录（details 含 dimension 字段）合并，缺省标「未标注」。

用法（在本仓库根目录之外同样可用，路径全部参数化）：
    python make_blind.py --src <原始包目录> [--out <赛事目录>]
                         [--scores <官方跑分目录>]

校验：
  1. 结构断言：盲版任何位置（递归）不存在 "answer" 键；
  2. 文本扫描：盲版文件原文不出现 `"answer"` 字样；
  3. 等价性：盲版 + 答案键可无损还原原文件（确认只删了 answer）；
  4. 题数：每届实际题数与元数据 total_questions 一致；
  5. 维度覆盖：打印未标注维度计数（有 --scores 时应为 0）。
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # 评测/
DEFAULT_OUT = ROOT / "试题" / "BaziQA-全球算命师大赛"


def strip_answers(node, path: str = "$"):
    """递归剥离题目里的 answer 键；返回剥离数量。非题目位置本就不该有 answer，发现即报错。"""
    n = 0
    if isinstance(node, dict):
        if "options" in node and "question_id" in node:
            assert "answer" in node, f"{path}: 题目缺少 answer 字段"
            del node["answer"]
            n += 1
        else:
            assert "answer" not in node, f"{path}: 非题目位置出现 answer 键"
        for k, v in node.items():
            n += strip_answers(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            n += strip_answers(v, f"{path}[{i}]")
    return n


def has_answer_key(node) -> bool:
    if isinstance(node, dict):
        return "answer" in node or any(has_answer_key(v) for v in node.values())
    if isinstance(node, list):
        return any(has_answer_key(v) for v in node)
    return False


def load_dimensions(scores_dir: Path | None) -> dict[tuple[str, str, int], str]:
    """从官方跑分 details 复用维度标签，键 (dataset, person_id, question_index)。"""
    dim = {}
    if not scores_dir or not scores_dir.is_dir():
        return dim
    for f in sorted(scores_dir.glob("contest8_*.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for d in s.get("details", []):
            dim[(d["dataset"], d["person_id"], d["question_index"])] = \
                d.get("dimension", "未标注")
    return dim


def main() -> int:
    ap = argparse.ArgumentParser(description="试题原始包 → questions/+answers/ 分离")
    ap.add_argument("--src", type=Path, required=True, help="含 answer 的原始 contest8_*.json 目录")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="赛事目录（其下建 questions/ 与 answers/）")
    ap.add_argument("--scores", type=Path, default=None, help="官方跑分目录（取 dimension 维度标签，可省）")
    a = ap.parse_args()

    q_dir = a.out / "questions"
    k_dir = a.out / "answers"
    q_dir.mkdir(parents=True, exist_ok=True)
    k_dir.mkdir(parents=True, exist_ok=True)
    dims = load_dimensions(a.scores)

    total = 0
    for src in sorted(a.src.glob("contest8_*.json")):
        original = json.loads(src.read_text(encoding="utf-8"))
        contest = original[0]["contest_id"]
        blind = copy.deepcopy(original)
        n = strip_answers(blind)

        # 结构断言：盲版任何位置无 answer 键
        assert not has_answer_key(blind), f"{src.name}: 盲版仍含 answer 键"

        # 答案键：仅 person_id + 题序 + 答案字母 + 维度标签
        missing_dim = 0
        key = [{
            "contest_id": contest,
            "total_questions": original[0].get("total_questions"),
            "note": "答案键：person_id + 题序 + 标准答案字母 + 维度标签；求解端禁读",
        }]
        for p in original[1:]:
            answers = []
            for i, q in enumerate(p["questions"], start=1):
                d = dims.get((contest, p["person_id"], i))
                if d is None:
                    d, missing_dim = "未标注", missing_dim + 1
                answers.append({"question_index": i, "answer": q["answer"],
                                "dimension": d})
            key.append({"person_id": p["person_id"], "answers": answers})

        # 等价性：盲版 + 答案键 == 原版（确认除 answer 外未动任何字段）
        rebuilt = copy.deepcopy(blind)
        for p_o, p_r in zip(original[1:], rebuilt[1:]):
            for q_o, q_r in zip(p_o["questions"], p_r["questions"]):
                q_r["answer"] = q_o["answer"]
        assert rebuilt == original, f"{src.name}: 剥离 answer 后其余字段不一致"

        # 题数与元数据一致
        actual = sum(len(p["questions"]) for p in original[1:])
        assert original[0].get("total_questions") in (None, actual), \
            f"{src.name}: 元数据 total_questions={original[0].get('total_questions')} 与实际 {actual} 不符"

        q_text = json.dumps(blind, ensure_ascii=False, indent=1) + "\n"
        # 文本扫描：盲版原文不得出现 "answer" 字样
        assert '"answer"' not in q_text, f"{src.name}: 盲版文本含 answer 字样"
        (q_dir / src.name).write_text(q_text, encoding="utf-8")
        (k_dir / src.name).write_text(
            json.dumps(key, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        total += n
        print(f"{src.name}: {len(original) - 1} 命主 {n} 题 -> "
              f"questions/（盲版）+ answers/（答案键，维度未标注 {missing_dim}）")
    print(f"OK: 共分离 {total} 题，questions/ 与 answers/ 已生成并校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
