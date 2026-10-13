#!/usr/bin/env python3
"""得分.json → 单文件 HTML 记分卡（模板 scorecard_template.html）。

沿用技能盘面图的品牌风格：logo 与品牌字体从母版 scripts/render/assets/
以 base64 内嵌（单文件便携），亮色卡片风。数据全部由 得分.json 注入，
模板不含任何硬编码分数。

得分.json 字段 schema（收录新模型时按此填写）：
    model, skill_mode（with-skill / without-skill）, skill_version, eval_date,
    benchmark,
    overall:      {total, correct, accuracy, no_answer}
    baseline:     {name, overall: {total, correct, accuracy},
                   per_contest: {contest: accuracy}, per_dimension: {维度: accuracy}}
    per_contest:  {contest: {total, correct, accuracy, no_answer}}
    per_dimension:{维度: {total, correct, accuracy, no_answer}}

用法：
    python render_scorecard.py [--score <得分.json>] [--out <输出.html>]
                               [--template <模板>] [--assets <render/assets>]
默认：--score 评测/ai模型纬度得分/kimi-k3/with-skill/得分.json，
输出与得分.json 同目录的 得分.html。
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # 评测/
SKILL = Path(__file__).resolve().parents[2]         # 技能母版根
DEFAULT_SCORE = ROOT / "ai模型纬度得分" / "kimi-k3" / "with-skill" / "得分.json"
DIM_ORDER = ["流年运势", "感情", "六亲", "事业", "性格", "学业", "财富", "健康", "其他"]

# 结构性占位符：值是装配层渲染的 HTML 片段或 base64 资源，填充时原样注入；
# 其余占位符均为文本字段，一律 HTML 转义防注入（与盘面图装配层同口径）。
STRUCTURAL = {"LOGO_B64", "FONT_B64", "DIM_BARS", "CONTEST_BARS"}


def asset_b64(assets: Path, name: str) -> str:
    f = assets / name
    return base64.b64encode(f.read_bytes()).decode("ascii") if f.is_file() else ""


def dim_bars(score: dict) -> str:
    rows = []
    dims = score["per_dimension"]
    base = score["baseline"].get("per_dimension", {})
    for d in DIM_ORDER + sorted(set(dims) - set(DIM_ORDER)):
        if d not in dims:
            continue
        s = dims[d]
        b = base.get(d)
        name = escape(d)
        ours = f'<div class="bar ours" style="width:{s["accuracy"]}%"></div>'
        ours += (f'<div class="bar base" style="width:{b}%"></div>'
                 if isinstance(b, (int, float)) else "")
        val = (f'<b>{s["accuracy"]}%</b>（{s["correct"]}/{s["total"]}）'
               + (f' <span style="color:var(--muted)">基线 {b}%</span>'
                  if isinstance(b, (int, float)) else ""))
        rows.append(f'<div class="dimrow"><div class="dimname">{name}</div>'
                    f'<div class="dimtrack">{ours}</div>'
                    f'<div class="dimval">{val}</div></div>')
    return "\n      ".join(rows)


def contest_bars(score: dict) -> str:
    rows = []
    base = score["baseline"].get("per_contest", {})
    for c in sorted(score["per_contest"]):
        s = score["per_contest"][c]
        b = base.get(c)
        label = escape(re.sub(r"^contest\d+_", "", c) + " 届")
        ours = f'<div class="bar ours" style="width:{s["accuracy"]}%"></div>'
        ours += (f'<div class="bar base" style="width:{b}%"></div>'
                 if isinstance(b, (int, float)) else "")
        val = f'<b>{s["accuracy"]}%</b>（{s["correct"]}/{s["total"]}）'
        if isinstance(b, (int, float)):
            diff = round(s["accuracy"] - b, 1)
            cls = "up" if diff >= 0 else "down"
            val += (f' <span style="color:var(--muted)">基线 {b}%</span>'
                    f' <span class="delta {cls}">'
                    f'{"+" if diff >= 0 else ""}{diff}pp</span>')
        rows.append(f'<div class="dimrow"><div class="yrname">{label}</div>'
                    f'<div class="dimtrack">{ours}</div>'
                    f'<div class="yrval">{val}</div></div>')
    return "\n      ".join(rows)


def render(score: dict, template: str, assets: Path, score_json_name: str) -> str:
    ov = score["overall"]
    bo = score["baseline"]["overall"]
    delta = round(ov["accuracy"] - bo["accuracy"], 1)
    values = {
        "TITLE": f"评测记分卡：{score['model']}（{score['skill_mode']}）",
        "LOGO_B64": asset_b64(assets, "lingyao-logo.png"),
        "FONT_B64": asset_b64(assets, "logo-font.ttf"),
        "MODEL": score["model"],
        "SKILL_MODE_LABEL": "加载技能" if score["skill_mode"] == "with-skill"
                            else "裸答对照",
        "BENCHMARK": score["benchmark"],
        "SKILL_VERSION": score.get("skill_version", "—"),
        "EVAL_DATE": score.get("eval_date", "—"),
        "OVERALL_ACC": f'{ov["accuracy"]}',
        "OVERALL_CORRECT": f'{ov["correct"]}',
        "OVERALL_TOTAL": f'{ov["total"]}',
        "NO_ANSWER": f'{ov.get("no_answer", 0)}',
        "BASELINE_NAME": score["baseline"].get("name", "官方基线"),
        "BASELINE_ACC": f'{bo["accuracy"]}',
        "DELTA_CLASS": "up" if delta >= 0 else "down",
        "DELTA_TEXT": f'（{"+" if delta >= 0 else ""}{delta}pp）',
        "DIM_BARS": dim_bars(score),
        "CONTEST_BARS": contest_bars(score),
        "SCORE_JSON": score_json_name,
    }
    out = template
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", v if k in STRUCTURAL else escape(str(v)))
    leftover = [p.split("}}")[0] for p in out.split("{{")[1:]]
    assert not leftover, f"模板存在未填充占位符: {leftover}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="得分.json → 单文件 HTML 记分卡")
    ap.add_argument("--score", type=Path, default=DEFAULT_SCORE)
    ap.add_argument("--out", type=Path, default=None,
                    help="默认与得分.json 同目录的 得分.html")
    ap.add_argument("--template", type=Path,
                    default=Path(__file__).resolve().parent / "scorecard_template.html")
    ap.add_argument("--assets", type=Path,
                    default=SKILL / "scripts" / "render" / "assets")
    a = ap.parse_args()

    score = json.loads(a.score.read_text(encoding="utf-8"))
    template = a.template.read_text(encoding="utf-8")
    out = a.out or a.score.with_name("得分.html")
    html = render(score, template, a.assets, a.score.name)
    out.write_text(html, encoding="utf-8")
    print(f"OK: {out}（{len(html)} 字符，logo/字体"
          f"{'已内嵌' if asset_b64(a.assets, 'lingyao-logo.png') else '未找到，已留空'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
