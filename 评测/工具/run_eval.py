#!/usr/bin/env python3
"""评测判分脚本：抽取求解代理答案 → 比对答案键 → 输出统计与报告。

答案文件约定：<submissions>/<contest>_<person_id>.md，每命主末尾恰好 5 行
`Q1: A` … `Q5: X`（X ∈ ABCD；答不出标 N 记 no_answer；行尾允许 # 注释）。
题数以 questions/ 盲版为准（允许单命主不足 5 题，如 2021 届 P033/P034）。

数据源全部参数化、不依赖任何外部仓库路径：
- --questions    盲版题目目录（枚举命主与题序）
- --answers-key  答案键目录（person_id + 题序 + 答案字母 + 维度标签）
- --submissions  待判答案 md 目录
- --out-json / --out-md  结果输出

基线：BaziQA 官方基线（Gemini 跑分）内嵌于本脚本，口径见
试题/BaziQA-全球算命师大赛/SOURCE.md。

零网络调用。用法：
    python run_eval.py [--questions <dir>] [--answers-key <dir>]
                       [--submissions <dir>] [--out-json <file>] [--out-md <file>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # 评测/
CONTEST_DIR = ROOT / "试题" / "BaziQA-全球算命师大赛"

# BaziQA 官方基线（来源见 SOURCE.md）：总体 + 分届 + 分维度
OFFICIAL_TOTAL = {"total": 200, "correct": 69, "accuracy": 34.5}
OFFICIAL_CONTEST = {
    "contest8_2021": {"total": 40, "accuracy": 27.5},
    "contest8_2022": {"total": 40, "accuracy": 40.0},
    "contest8_2023": {"total": 40, "accuracy": 27.5},
    "contest8_2024": {"total": 40, "accuracy": 35.0},
    "contest8_2025": {"total": 40, "accuracy": 42.5},
}
OFFICIAL_DIM = {
    "流年运势": {"total": 37, "accuracy": 40.5},
    "感情": {"total": 49, "accuracy": 36.7},
    "六亲": {"total": 29, "accuracy": 27.6},
    "事业": {"total": 25, "accuracy": 24.0},
    "性格": {"total": 20, "accuracy": 45.0},
    "学业": {"total": 12, "accuracy": 41.7},
    "财富": {"total": 13, "accuracy": 30.8},
    "健康": {"total": 13, "accuracy": 23.1},
    "其他": {"total": 2, "accuracy": 50.0},
}
DIM_ORDER = ["流年运势", "感情", "六亲", "事业", "性格", "学业", "财富", "健康", "其他"]

ANS_RE = re.compile(r"^\s*Q([1-5])\s*[:：]\s*([A-DNdn])\b", re.M)
FILE_RE = re.compile(r"^(contest\d+_\d{4})_(.+)$")


def load_questions(q_dir: Path) -> dict[str, list[dict]]:
    """盲版题目：contest -> 命主数组（仅取 person_id 与题数，不读题面）。"""
    out = {}
    for f in sorted(q_dir.glob("contest8_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d[0]["contest_id"]] = d[1:]
    return out


def load_answer_key(k_dir: Path) -> dict[tuple[str, str], dict[int, dict]]:
    """答案键：(contest, person_id) -> {题序: {answer, dimension}}。"""
    out = {}
    for f in sorted(k_dir.glob("contest8_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        contest = d[0]["contest_id"]
        for p in d[1:]:
            out[(contest, p["person_id"])] = {
                a["question_index"]: a for a in p["answers"]}
    return out


def parse_answer_file(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8")
    ans: dict[int, str] = {}
    for m in ANS_RE.finditer(text):
        q = int(m.group(1))
        if q not in ans:  # 同一题取首次出现
            ans[q] = m.group(2).upper()
    return ans


def acc(correct: int, total: int) -> float:
    return round(correct / total * 100, 1) if total else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="评测判分：submissions 答案文件 vs 答案键")
    ap.add_argument("--questions", type=Path, default=CONTEST_DIR / "questions")
    ap.add_argument("--answers-key", type=Path, default=CONTEST_DIR / "answers")
    ap.add_argument("--submissions", type=Path,
                    default=ROOT / "ai答案" / "kimi-k3" / "with-skill")
    ap.add_argument("--out-json", type=Path, default=ROOT / "eval_result.json")
    ap.add_argument("--out-md", type=Path, default=ROOT / "eval_report.md")
    a = ap.parse_args()

    datasets = load_questions(a.questions)
    keys = load_answer_key(a.answers_key)

    # 索引答案文件：contest -> person_id -> {q: letter}
    files: dict[tuple[str, str], dict[int, str]] = {}
    if a.submissions.is_dir():
        for f in sorted(a.submissions.glob("*.md")):
            m = FILE_RE.match(f.stem)
            if not m:
                print(f"WARN: 跳过无法解析的文件名 {f.name}", file=sys.stderr)
                continue
            files[(m.group(1), m.group(2))] = parse_answer_file(f)

    details = []
    per_contest: dict[str, dict[str, int]] = {}
    per_dim: dict[str, dict[str, int]] = {}
    tot = cor = noans = 0
    missing: list[str] = []
    for contest, persons in datasets.items():
        cs = per_contest.setdefault(contest, {"total": 0, "correct": 0, "no_answer": 0})
        for p in persons:
            pid = p["person_id"]
            got = files.get((contest, pid))
            if got is None:
                missing.append(f"{contest}/{pid}")
                got = {}
            key = keys.get((contest, pid), {})
            for i in range(1, len(p["questions"]) + 1):
                letter = got.get(i)
                unanswered = letter in (None, "N")
                k = key.get(i, {})
                ok = (not unanswered) and letter == k.get("answer")
                dim = k.get("dimension", "未标注")
                ds = per_dim.setdefault(dim, {"total": 0, "correct": 0, "no_answer": 0})
                for s in (cs, ds):
                    s["total"] += 1
                    s["correct"] += ok
                    s["no_answer"] += unanswered
                tot += 1
                cor += ok
                noans += unanswered
                details.append({
                    "dataset": contest, "person_id": pid, "question_index": i,
                    "ai_answer": letter or "N",
                    "correct_answer": k.get("answer", "?"), "is_correct": ok,
                    "dimension": dim,
                })

    if missing:
        print(f"WARN: {len(missing)} 位命主缺答案文件，按全未答计："
              + ", ".join(missing), file=sys.stderr)

    stats: dict = {"总体": {"total": tot, "correct": cor,
                          "accuracy": acc(cor, tot), "no_answer": noans}}
    for c, s in per_contest.items():
        stats[c] = {**s, "accuracy": acc(s["correct"], s["total"])}
    dim_stats = {}
    for d in DIM_ORDER + sorted(set(per_dim) - set(DIM_ORDER)):
        if d in per_dim:
            s = per_dim[d]
            dim_stats[d] = {**s, "accuracy": acc(s["correct"], s["total"])}
    stats["分维度"] = dim_stats

    result = {"stats": stats, "details": details}
    a.out_json.parent.mkdir(parents=True, exist_ok=True)
    a.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")

    ours = stats["总体"]
    lines = [
        "# BaziQA 评测报告", "",
        "## 总览", "",
        "| 口径 | 正确/总题数 | 准确率 | 未答 |", "|---|---|---|---|",
        f"| 本次评测 | {ours['correct']}/{ours['total']} | {ours['accuracy']}% | {ours['no_answer']} |",
        f"| 官方基线（Gemini） | {OFFICIAL_TOTAL['correct']}/{OFFICIAL_TOTAL['total']}"
        f" | {OFFICIAL_TOTAL['accuracy']}% | 0 |",
        "", f"> 基线口径见 试题/BaziQA-全球算命师大赛/SOURCE.md。",
        "", "## 分届准确率", "",
        "| 届别 | 本次 | 官方 |", "|---|---|---|",
    ]
    for c in sorted(per_contest):
        s = stats[c]
        off = OFFICIAL_CONTEST.get(c, {})
        lines.append(f"| {c} | {s['correct']}/{s['total']} = {s['accuracy']}%"
                     f"（未答 {s['no_answer']}） | {off.get('accuracy', '—')}% |")
    lines += ["", "## 分维度准确率", "",
              "| 维度 | 本次 | 官方 |", "|---|---|---|"]
    for d, s in dim_stats.items():
        off = OFFICIAL_DIM.get(d, {})
        lines.append(f"| {d} | {s['correct']}/{s['total']} = {s['accuracy']}%"
                     f"（未答 {s['no_answer']}） | {off.get('accuracy', '—')}% |")
    lines += ["", "## 错题清单（错因留空，待人工/后续填写）", "",
              "| 届别 | 命主 | 题序 | 维度 | 我答 | 正解 | 错因 |",
              "|---|---|---|---|---|---|---|"]
    for d in details:
        if not d["is_correct"]:
            lines.append(f"| {d['dataset']} | {d['person_id']} | Q{d['question_index']}"
                         f" | {d['dimension']} | {d['ai_answer']} | {d['correct_answer']} |  |")
    a.out_md.parent.mkdir(parents=True, exist_ok=True)
    a.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"总准确率: {ours['correct']}/{ours['total']} = {ours['accuracy']}%"
          f"（未答 {ours['no_answer']}；官方基线 {OFFICIAL_TOTAL['accuracy']}%）")
    print(f"写出 {a.out_json} / {a.out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
