# scripts/render/markdown.py
"""ChartData → 自包含 Markdown（输出格式契约 v1.0）。

纯文本、无代码块、无表格嵌套；审计信息放末尾；字段名用中文；
不包含任何命理判断（P1）。
"""


def render(chart) -> str:
    L = []
    L.append(f"# 命盘：{chart.name}")
    L.append("")
    L.append(f"- 性别：{chart.gender}")
    L.append(f"- 出生地：{chart.birthplace}")
    L.append(f"- 输入时间：{chart.birth_clock}")
    L.append(f"- 真太阳时：{chart.true_solar_time}")
    if chart.is_late_zi:
        L.append(
            "- ⚠️ 晚子时：本造落于真太阳时 23:00–24:00，"
            "已按「子初换日」归入次日。另存「子正换日」一派，"
            "日柱与时柱将不同，结论需谨慎。"
        )
    L.append("")

    L.append("## 四柱")
    L.append("")
    for key, label, p in (("year", "年柱", chart.year),
                          ("month", "月柱", chart.month),
                          ("day", "日柱", chart.day),
                          ("hour", "时柱", chart.hour)):
        god = p.gan_ten_god or ("日主" if key == "day" else "")
        line = f"- {label}：{p.gan}{p.zhi}"
        if god:
            line += f"（{god}）"
        changsheng = chart.terrain.get(key)
        if changsheng:
            line += f" · {changsheng}"
        L.append(line)
    L.append("")

    L.append("## 地支藏干")
    L.append("")
    for label, p in (("年支", chart.year), ("月支", chart.month),
                     ("日支", chart.day), ("时支", chart.hour)):
        if p.hidden_stems:
            pairs = "、".join(f"{s}（{g}）"
                              for s, g in zip(p.hidden_stems, p.hidden_ten_gods))
            L.append(f"- {label} {p.zhi}：{pairs}")
    L.append("")

    L.append("## 四柱空亡")
    L.append("")
    L.append(f"- 日柱空亡：{chart.void['day']}；时柱空亡：{chart.void['hour']}")
    L.append("")

    L.append("## 纳音")
    L.append("")
    for label, p in (("年柱", chart.year), ("月柱", chart.month),
                     ("日柱", chart.day), ("时柱", chart.hour)):
        if p.na_yin:
            L.append(f"- {label}：{p.na_yin}")
    L.append("")

    L.append("## 神煞")
    L.append("")
    if chart.shen_sha:
        for s in chart.shen_sha:
            L.append(f"- {s}")
    else:
        L.append("- （本造未取神煞）")
    L.append("")

    L.append("## 节令")
    L.append("")
    L.append(f"- 月令：{chart.month_ling}")
    L.append(f"- 生于 {chart.solar_term_before} 之后、{chart.solar_term_after} 之前")
    L.append(f"- 胎元：{chart.tai_yuan}　命宫：{chart.ming_gong}")
    L.append("")

    L.append("## 大运")
    L.append("")
    direction = "顺行" if chart.luck_is_forward else "逆行"
    if chart.luck_pillars:
        L.append(f"- 排法：{direction}；起运：{chart.start_age_text}"
                 f"（{chart.luck_pillars[0].start_age:.2f} 岁）")
    else:
        L.append(f"- 排法：{direction}；起运：{chart.start_age_text}")
    for lp in chart.luck_pillars:
        L.append(f"- 第 {lp.index} 步：{lp.gan}{lp.zhi}"
                 f"（{lp.start_age:.2f} 岁起，{lp.start_year} 年）")
    L.append("")

    L.append("## 流年")
    L.append("")
    for year, gz in chart.flow_years:
        L.append(f"- {year} {gz}")
    L.append("")

    L.append("## 流月")
    L.append("")
    for label, gz in chart.flow_months:
        L.append(f"- {label}：{gz}")
    L.append("")

    L.append("---")
    L.append("## 排盘审计")
    L.append("")
    L.append(f"- 时区：{chart.tz_used}（夏令时：{'是' if chart.is_dst else '否'}）")
    L.append(f"- 经度修正：{chart.lon_correction_min:+.2f} 分 / "
             f"均时差：{chart.eot_minutes:+.2f} 分 / "
             f"合计修正：{chart.lon_correction_min + chart.eot_minutes:+.2f} 分")
    L.append("- 日界规则：子初换日（真太阳时 23:00）")
    L.append(f"- 历法库：tyme4py {chart.library_version}")
    L.append(f"- 输出 schema：{chart.schema_version}")

    return "\n".join(L)
