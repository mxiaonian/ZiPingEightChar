#!/usr/bin/env python3
# 副本 LY-20261007-AC63 · 授权对象 normal
"""子平排盘 —— 唯一对外接口。

用法：
    python cast_chart.py --name 张三 --gender 男 \
        --birth "1990-05-14 08:30" --place "四川省成都市"
输出：Markdown 到 stdout。

退出码：0 成功；2 输入不可用（应追问用户）；3 库内部错误（报错，不猜）；4 授权不可用（软锁，见 LICENSE.md）。
"""
import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 引导：无论从哪个目录调用，scripts/ 下的顶层包（geo/astro/chart/render）都可导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 免安装：优先使用随包内置的依赖（vendor/，版本锁定 tyme4py==1.5.0 + tzdata）
# vendor 目录不存在时回退到环境中已安装的包（开发模式）
_VENDOR = Path(__file__).resolve().parents[1] / "vendor"
if _VENDOR.is_dir():
    sys.path.insert(0, str(_VENDOR))


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="cast_chart.py",
        description="子平真诠八字排盘：姓名/性别/出生时刻/出生地 → 结构化命盘 Markdown（只排盘，不断命）",
    )
    ap.add_argument("--name", required=True, help="姓名")
    ap.add_argument("--gender", required=True, choices=["男", "女"],
                    help="性别：男 或 女")
    ap.add_argument("--birth", required=True,
                    help='出生时刻（当地钟表时间），格式 "YYYY-MM-DD HH:MM"，时刻必需')
    ap.add_argument("--place", required=True,
                    help="出生地，精确到地级市一级，如「四川省成都市」")
    ap.add_argument("--html", nargs="?", const="", default=None,
                    help="可选：同时生成 HTML 盘面图（给路径参数，或省略则写 ./命盘_<姓名>.html）")
    a = ap.parse_args()

    # 软授权锁：定制副本（含 data/.license.json）按授权次数/期限放行；母版无状态文件直接放行
    import _license_gate as _gate
    _deny = _gate.check(Path(__file__).resolve().parents[1])
    if _deny:
        print(f"ERROR: {_deny}", file=sys.stderr)
        return 4

    try:
        # 延迟导入：让 --help 不依赖下游模块就绪；导入失败按库内部错误（退出码 3）处理
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

        # 排盘时刻 = 换日后的日历日 + 真太阳时的时分秒
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
        # 大运步数须覆盖流年末端（默认 8 步；年长者自动加步）
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

        # L2 渲染：stdout 只出 Markdown
        print(render(chart))
        _gate.consume(Path(__file__).resolve().parents[1])

        # 可选：同步生成 HTML 盘面图（渲染失败不影响 stdout 契约）
        if a.html is not None:
            try:
                from render.html import build_html
                html_path = (Path(a.html) if a.html
                             else Path(f"命盘_{a.name}.html"))
                html_path.write_text(build_html(chart), encoding="utf-8")
                print(f"HTML 盘面：{html_path.resolve()}", file=sys.stderr)
            except Exception:
                print("WARN: HTML 盘面生成失败（命盘不受影响）", file=sys.stderr)

        # 自更新提示：只读本地缓存往 stderr 打一行；缓存过期则后台线程刷新，
        # 主流程不等它（用当次缓存）。任何异常静默，绝不影响 stdout 命盘契约。
        try:
            import self_update as _su
            _root = Path(__file__).resolve().parents[1]
            _msg = _su.notify_message(_root)
            if _msg:
                print(_msg, file=sys.stderr)
            _su.refresh_cache_async(_root)
        except Exception:
            pass
        return 0
    except Exception:
        print("ERROR: 排盘内部错误。请把以下信息原样报告给用户，"
              "不要自行猜测命盘。", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
