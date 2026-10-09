#!/usr/bin/env python3
"""命主档案建档/更新 —— 排盘一次并写入 memory/archives/。

用法：
    python memory_save.py --name 张三 --gender 男 \
        --birth "1990-05-14 08:30" --place "四川省成都市"
输出：档案文件路径到 stdout。

建档即一次排盘：授权副本照常过软锁、扣减一次（与 cast_chart.py 同一 check/consume 位置）。
同主键（四柱+性别+hash6）档案已存在时只刷新 frontmatter 与「## 盘面」，
正文其余小节（归纳、反馈与澄清等）原样保留。档案规范见 memory/README.md。

退出码：0 成功；2 输入不可用；3 库内部错误；4 授权不可用（软锁，见 LICENSE.md）。
"""
import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 引导：无论从哪个目录调用，scripts/ 下的顶层包（geo/astro/chart/render）都可导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 免安装：优先使用随包内置的依赖（vendor/，版本锁定 tyme4py==1.5.0 + tzdata）
_VENDOR = Path(__file__).resolve().parents[1] / "vendor"
if _VENDOR.is_dir():
    sys.path.insert(0, str(_VENDOR))

import _memory_store as store


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="memory_save.py",
        description="命主档案建档/更新：排盘一次并写入 memory/archives/（stdout 打印档案路径）",
    )
    ap.add_argument("--name", required=True, help="姓名")
    ap.add_argument("--gender", required=True, choices=["男", "女"],
                    help="性别：男 或 女")
    ap.add_argument("--birth", required=True,
                    help='出生时刻（当地钟表时间），格式 "YYYY-MM-DD HH:MM"，时刻必需')
    ap.add_argument("--place", required=True,
                    help="出生地，精确到地级市一级，如「四川省成都市」")
    ap.add_argument("--memory-root", default=None,
                    help=f"档案根目录（默认技能根 memory/；亦可用环境变量 {store.ENV_VAR}）")
    a = ap.parse_args()

    # 软授权锁：与 cast_chart.py 同位置——建档即一次排盘，先 check，成功后 consume
    import _license_gate as _gate
    _deny = _gate.check(Path(__file__).resolve().parents[1])
    if _deny:
        print(f"ERROR: {_deny}", file=sys.stderr)
        return 4

    try:
        # 排盘管线与 cast_chart.py 同一调用序列（geo → astro → chart → render）
        from geo.cities import resolve_location, LocationError
        from astro.timezone_resolve import to_utc
        from astro.solar_time import to_true_solar_time
        from astro.day_boundary import resolve_calendar_day
        from chart.tyme_adapter import cast
        from chart.luck import (
            childhood_luck, compute_luck, decade_pillars, flow_months,
            flow_years, is_forward, luck_label_for_year,
        )
        from chart.model import build_chart_data
        from render.markdown import render

        # L0-a 地点解析（失败抛 LocationError → 退出码 2）
        try:
            loc = resolve_location(a.place)
        except LocationError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2

        # L0-b 出生时刻解析
        try:
            clock = datetime.strptime(a.birth.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            print("ERROR: 出生时间格式应为 YYYY-MM-DD HH:MM；"
                  "若用户只给了日期，请追问具体时刻。", file=sys.stderr)
            return 2

        # L0-c 当地钟表时间 → UTC（含历史时区/夏令时审计）
        utc, tz_audit = to_utc(clock, loc)

        # L0-d UTC → 真太阳时（经度修正 + 均时差）
        tst, st_audit = to_true_solar_time(utc, loc.lon)

        # L0-e 子初换日：真太阳时 23:00–24:00 归入次日
        day, bd_audit = resolve_calendar_day(tst)

        cast_dt = day.replace(hour=tst.hour, minute=tst.minute, second=tst.second)

        # L1-a 排盘（tyme4py 唯一接触面）
        raw = cast(cast_dt, a.gender)

        # L1-b 起运、大运、流年、流月、小运
        forward = is_forward(a.gender, raw["year"]["gan"])
        luck = compute_luck(
            birth_tst=tst,
            prev_jie_time=raw["prev_jie"]["time"],
            next_jie_time=raw["next_jie"]["time"],
            forward=forward,
        )
        this_year = datetime.now().year
        n_pillars = max(
            8,
            int((this_year + 9 - cast_dt.year - luck["start_age_years"]) / 10) + 2,
        )
        decade = decade_pillars(
            raw["month"]["gan"], raw["month"]["zhi"], forward,
            luck["start_age_years"], cast_dt.year, n=n_pillars,
        )
        years = [
            (y, gz, luck_label_for_year(y, decade))
            for y, gz in flow_years(cast_dt.year, this_year, 10)
        ]
        months = flow_months(this_year)
        childhood = childhood_luck(
            raw["hour"]["gan"], raw["hour"]["zhi"], forward,
            luck["start_age_years"], cast_dt.year,
        )

        # L1-c 组装 ChartData
        chart = build_chart_data(
            name=a.name, gender=a.gender, place=a.place, clock=a.birth,
            loc=loc, tz_audit=tz_audit, st_audit=st_audit, bd_audit=bd_audit,
            raw=raw, luck=luck, luck_pillars=decade,
            flow_years=years, flow_months=months, childhood_luck=childhood,
        )

        # L2 渲染命盘 Markdown（嵌入档案「## 盘面」，不直接打印）
        chart_md = render(chart)

        # —— 建档/更新 ——
        pillars = [f"{chart.year.gan}{chart.year.zhi}",
                   f"{chart.month.gan}{chart.month.zhi}",
                   f"{chart.day.gan}{chart.day.zhi}",
                   f"{chart.hour.gan}{chart.hour.zhi}"]
        root = store.resolve_root(a.memory_root, __file__)
        arch_dir = root / "archives"
        arch_dir.mkdir(parents=True, exist_ok=True)
        path = arch_dir / store.archive_name(
            pillars, a.gender, store.key_hash(a.birth, a.place, a.gender))

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        meta = {
            "name": a.name, "gender": a.gender, "birth_clock": a.birth.strip(),
            "birthplace": a.place.strip(), "true_solar_time": chart.true_solar_time,
            "pillars": pillars, "day_master": chart.day_master,
            "created_at": now, "updated_at": now,
        }
        if path.is_file():
            old_meta, body = store.parse_frontmatter(
                path.read_text(encoding="utf-8"))
            meta["created_at"] = old_meta.get("created_at") or now
            body = store.replace_section(body, "盘面", chart_md)
        else:
            body = store.skeleton(a.name, a.gender, chart_md)
        path.write_text(store.dump_frontmatter(meta) + body, encoding="utf-8")

        _gate.consume(Path(__file__).resolve().parents[1])
        print(path)
        return 0
    except SystemExit:
        raise
    except Exception:
        print("ERROR: 建档内部错误。请把以下信息原样报告给用户，"
              "不要自行猜测命盘。", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
