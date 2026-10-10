#!/usr/bin/env python3
"""命主档案建档/更新 —— 排盘一次并写入 memory/archives/。

用法：
    python memory_save.py --name 张三 --gender 男 \
        --birth "1990-05-14 08:30" --place "四川省成都市"

    # 换盘（更新既有档案盘面段）：按档案重排并替换「## 盘面」，frontmatter 同步
    python memory_save.py --update-chart memory/archives/丙子庚子庚辰丙子-女-2825d1.md \
        [--day-boundary 子正] [--birth "校正后时刻"] [--place "校正后出生地"]
输出：档案文件路径到 stdout。

建档即一次排盘：授权副本照常过软锁、扣减一次（与 cast_chart.py 同一 check/consume 位置）。
同主键（四柱+性别+hash6）档案已存在时只刷新 frontmatter 与「## 盘面」，
正文其余小节（归纳、反馈与澄清等）原样保留。档案规范见 memory/README.md。

换盘模式（--update-chart）：姓名/性别/出生信息默认读档案 frontmatter，
--birth/--place 用于时辰/地点校正，--day-boundary 子正 切换日界规则（默认子初）。
换盘后「## 盘面」只保留新盘（工作盘唯一），旧盘信息由使用方记入「## 反馈与澄清」；
frontmatter 的 pillars/day_master/true_solar_time 同步为新盘，文件改为新主键名
（目标已存在且非同一文件时报错退出 2，不覆盖）。四柱有变动时 stderr 列出变动柱，
提示使用方把受影响推断条目（归纳、流年大事）标记【待复核】。

退出码：0 成功；2 输入不可用；3 库内部错误；4 授权不可用（软锁，见 LICENSE.md）。
"""
import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 引导：无论从哪个目录调用，scripts/ 下的顶层包（geo/astro/chart/render）都可导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _runtime_guard  # noqa: F401  import 即检查：Python < 3.10 时中文报错退出（码 3）

# 免安装：优先使用随包内置的依赖（vendor/，版本锁定 tyme4py==1.5.0 + tzdata）
_VENDOR = Path(__file__).resolve().parents[1] / "vendor"
if _VENDOR.is_dir():
    sys.path.insert(0, str(_VENDOR))

import _memory_store as store

_PILLAR_LABELS = ("年柱", "月柱", "日柱", "时柱")

# render 层日界文案写定（scripts/render/ 不在此处改动），换盘子正时改写这两行
_AUDIT_ZICHU = "- 日界规则：子初换日（真太阳时 23:00）"
_AUDIT_ZIZHENG = "- 日界规则：子正换日（真太阳时 00:00）"
_WARN_ZICHU = ("- ⚠️ 晚子时：本造落于真太阳时 23:00–24:00，"
               "已按「子初换日」归入次日。另存「子正换日」一派，"
               "日柱与时柱将不同，结论需谨慎。")
_WARN_ZIZHENG = ("- ⚠️ 晚子时：本造落于真太阳时 23:00–24:00，"
                 "已按「子正换日」定盘（日界 0:00，不换日）。"
                 "另存「子初换日」一派，日柱与时柱将不同，结论需谨慎。")


def _cast_chart(name: str, gender: str, birth: str, place: str,
                day_boundary: str = "子初"):
    """排盘管线（geo → astro → chart → render），与 cast_chart.py 同一调用序列。

    返回 (命盘 Markdown, 四柱 list, 日主, 真太阳时 str)；地点/时刻不可用抛
    LocationError/ValueError（由调用方映射退出码 2）。
    """
    from geo.cities import resolve_location
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
    loc = resolve_location(place)

    # L0-b 出生时刻解析
    clock = datetime.strptime(birth.strip(), "%Y-%m-%d %H:%M")

    # L0-c 当地钟表时间 → UTC（含历史时区/夏令时审计）
    utc, tz_audit = to_utc(clock, loc)

    # L0-d UTC → 真太阳时（经度修正 + 均时差）
    tst, st_audit = to_true_solar_time(utc, loc.lon)

    # L0-e 日界归算：默认子初换日（真太阳时 23:00–24:00 归入次日）
    day, bd_audit = resolve_calendar_day(tst, rule=day_boundary)

    cast_dt = day.replace(hour=tst.hour, minute=tst.minute, second=tst.second)

    # L1-a 排盘（tyme4py 唯一接触面）
    raw = cast(cast_dt, gender)

    # L1-b 起运、大运、流年、流月、小运
    forward = is_forward(gender, raw["year"]["gan"])
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
        name=name, gender=gender, place=place, clock=birth,
        loc=loc, tz_audit=tz_audit, st_audit=st_audit, bd_audit=bd_audit,
        raw=raw, luck=luck, luck_pillars=decade,
        flow_years=years, flow_months=months, childhood_luck=childhood,
    )

    # L2 渲染命盘 Markdown（嵌入档案「## 盘面」，不直接打印）
    chart_md = render(chart)
    if day_boundary == "子正":
        # render 层日界文案固定为子初口径，换盘子正时改写警示条与审计行
        chart_md = chart_md.replace(_WARN_ZICHU, _WARN_ZIZHENG)
        chart_md = chart_md.replace(_AUDIT_ZICHU, _AUDIT_ZIZHENG)

    pillars = [f"{chart.year.gan}{chart.year.zhi}",
               f"{chart.month.gan}{chart.month.zhi}",
               f"{chart.day.gan}{chart.day.zhi}",
               f"{chart.hour.gan}{chart.hour.zhi}"]
    return chart_md, pillars, chart.day_master, chart.true_solar_time


def _update_chart(a) -> int:
    """换盘模式：重排并替换既有档案的「## 盘面」段，frontmatter 与主键名同步。"""
    path = Path(a.update_chart).expanduser().resolve()
    if not path.is_file():
        print(f"ERROR: 档案不存在：{path}", file=sys.stderr)
        return 2
    meta, body = store.parse_frontmatter(path.read_text(encoding="utf-8"))
    if not meta:
        print("ERROR: 档案无 frontmatter，无法换盘；请检查文件或用完整建档。",
              file=sys.stderr)
        return 2
    name = str(meta.get("name", "")).strip()
    gender = str(meta.get("gender", "")).strip()
    birth = (a.birth or str(meta.get("birth_clock", ""))).strip()
    place = (a.place or str(meta.get("birthplace", ""))).strip()
    if not name or gender not in ("男", "女") or not birth or not place:
        print("ERROR: 档案 frontmatter 缺 name/gender/birth_clock/birthplace，"
              "无法重排；请补全档案或改用完整建档。", file=sys.stderr)
        return 2

    from geo.cities import LocationError
    try:
        chart_md, pillars, day_master, tst_str = _cast_chart(
            name, gender, birth, place, a.day_boundary)
    except LocationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except ValueError:
        print("ERROR: 出生时间格式应为 YYYY-MM-DD HH:MM；"
              "若用户只给了日期，请追问具体时刻。", file=sys.stderr)
        return 2

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    old_pillars = meta.get("pillars", [])
    if isinstance(old_pillars, str):
        old_pillars = old_pillars.split()
    meta.update({
        "name": name, "gender": gender, "birth_clock": birth, "birthplace": place,
        "true_solar_time": tst_str, "pillars": pillars, "day_master": day_master,
        "created_at": meta.get("created_at") or now, "updated_at": now,
    })
    body = store.replace_section(body, "盘面", chart_md)

    # 四柱/hash6 变动时改为新主键名；目标已存在则拒绝覆盖
    new_path = path.with_name(store.archive_name(
        pillars, gender, store.key_hash(birth, place, gender)))
    if new_path != path:
        if new_path.exists():
            print(f"ERROR: 新盘主键档案已存在：{new_path}；"
                  f"为避免覆盖，本次未写入。请先核对两份档案。", file=sys.stderr)
            return 2
        new_path.write_text(store.dump_frontmatter(meta) + body, encoding="utf-8")
        path.unlink()
    else:
        path.write_text(store.dump_frontmatter(meta) + body, encoding="utf-8")

    changed = [f"{_PILLAR_LABELS[i]} {old_pillars[i]}→{pillars[i]}"
               for i in range(min(len(old_pillars), 4))
               if old_pillars[i] != pillars[i]]
    if changed:
        print(f"注意：{'、'.join(changed)} 已变。受变动柱影响的已有推断条目"
              f"（归纳、流年大事）须复核并标【待复核】，复核前不得继续引用；"
              f"旧盘四柱与换盘原因请记入「## 反馈与澄清」。", file=sys.stderr)
    print(new_path)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="memory_save.py",
        description="命主档案建档/更新：排盘一次并写入 memory/archives/（stdout 打印档案路径）",
    )
    ap.add_argument("--name", default=None, help="姓名")
    ap.add_argument("--gender", default=None, choices=["男", "女"],
                    help="性别：男 或 女")
    ap.add_argument("--birth", default=None,
                    help='出生时刻（当地钟表时间），格式 "YYYY-MM-DD HH:MM"，时刻必需；'
                         "换盘模式下为时辰校正覆盖值")
    ap.add_argument("--place", default=None,
                    help="出生地，精确到地级市一级，如「四川省成都市」；"
                         "换盘模式下为地点校正覆盖值")
    ap.add_argument("--update-chart", default=None, metavar="档案路径",
                    help="换盘模式：按档案重排并替换其「## 盘面」段，"
                         "frontmatter 与文件名同步为新盘")
    ap.add_argument("--day-boundary", default="子初", choices=["子初", "子正"],
                    help="日界规则：子初（默认，真太阳时 23:00 换日）或 子正（0:00 换日）；"
                         "仅换盘模式可用")
    ap.add_argument("--memory-root", default=None,
                    help=f"档案根目录（默认技能根 memory/；亦可用环境变量 {store.ENV_VAR}）")
    a = ap.parse_args()

    if a.update_chart is None:
        missing = [k for k in ("name", "gender", "birth", "place")
                   if getattr(a, k) is None]
        if missing:
            print(f"ERROR: 建档缺参数：{'、'.join('--' + k for k in missing)}。"
                  f"（换盘请用 --update-chart <档案路径>）", file=sys.stderr)
            return 2
        if a.day_boundary != "子初":
            print("ERROR: --day-boundary 仅换盘模式（--update-chart）可用；"
                  "建档固定子初换日。", file=sys.stderr)
            return 2
    elif a.name is not None or a.gender is not None:
        print("ERROR: 换盘模式不支持 --name/--gender（姓名、性别以档案为准）。",
              file=sys.stderr)
        return 2

    # 软授权锁：与 cast_chart.py 同位置——建档/换盘即一次排盘，先 check，成功后 consume
    import _license_gate as _gate
    _deny = _gate.check(Path(__file__).resolve().parents[1])
    if _deny:
        print(f"ERROR: {_deny}", file=sys.stderr)
        return 4

    try:
        if a.update_chart is not None:
            rc = _update_chart(a)
            if rc == 0:
                _gate.consume(Path(__file__).resolve().parents[1])
            return rc

        # L0/L1/L2 排盘管线（地点/时刻不可用 → 退出码 2）
        from geo.cities import LocationError
        try:
            chart_md, pillars, day_master, tst_str = _cast_chart(
                a.name, a.gender, a.birth, a.place)
        except LocationError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        except ValueError:
            print("ERROR: 出生时间格式应为 YYYY-MM-DD HH:MM；"
                  "若用户只给了日期，请追问具体时刻。", file=sys.stderr)
            return 2

        # —— 建档/更新 ——
        root = store.resolve_root(a.memory_root, __file__)
        arch_dir = root / "archives"
        arch_dir.mkdir(parents=True, exist_ok=True)
        path = arch_dir / store.archive_name(
            pillars, a.gender, store.key_hash(a.birth, a.place, a.gender))

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        meta = {
            "name": a.name, "gender": a.gender, "birth_clock": a.birth.strip(),
            "birthplace": a.place.strip(), "true_solar_time": tst_str,
            "pillars": pillars, "day_master": day_master,
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
