#!/usr/bin/env python3
"""脱敏档案导出 —— 从 memory 档案生成结构化脱敏包（JSON）到 share/pending/。

用法：
    python share_export.py --archive memory/archives/庚午辛巳己卯戊辰-男-a1b2c3.md
    python share_export.py --birth "1990-05-14 08:30" --place "四川省成都市" --gender 男

脱敏规格（见 share/README.md）：不含姓名；出生信息只保留年月日与时辰（不留分钟
与钟表时间）；地域保留到城市级（省+地级市，区县及以下删除）；事件带类目与简介
（note），简介中城市级地名保留（规则蒸馏要用方位信息），姓名、详细住址
（小区/门牌/街道号）、身份证/电话等直接定位信息一律删除；归纳、盘面细节等
正文自由文本不入包。盘 hash = sha1(四柱+出生地) 前 8 位，用于去重与撤回。

完整度门槛：性别/四柱/大运齐全 + 至少一条反馈事件（任意核实状态）；
不满足拒绝导出，退出码 2 并说明缺什么。事件简介缺失（档案未写事件内容）
不挡导出，JSON 中如实反映（events 为空或 note 为 null）。
换盘残留提示：导出时若 pending/ 中已有同出生日、同性别但盘 hash 不同的
旧包（多为换盘/信息更正后的孤儿包），stderr 打 WARN 列出路径，提醒人工清理
（只提示，不自动删）。
退出码：0 成功；2 不可用/不完整；3 内部错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _runtime_guard  # noqa: F401  import 即检查：Python < 3.10 时中文报错退出（码 3）
import _memory_store as store

SCHEMA = "share/v1"
PLACEHOLDERS = {"（无）", "（未记录）", "无", "未记录"}

# 事件/关注方向类目化：首个命中的类目生效，都不命中归「其他」
CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("婚姻", ("婚姻", "结婚", "离婚", "配偶", "夫妻", "婚变", "再婚")),
    ("感情", ("感情", "恋爱", "桃花", "对象", "分手", "复合")),
    ("事业", ("事业", "工作", "升职", "跳槽", "调动", "失业", "创业", "辞职", "职务", "官非")),
    ("财运", ("财运", "破财", "投资", "收入", "赚钱", "欠债", "债务", "置业", "买房")),
    ("健康", ("健康", "生病", "手术", "伤病", "身体", "住院", "疾病", "意外")),
    ("学业", ("学业", "考试", "升学", "考研", "高考", "留学", "读书", "大学")),
    ("六亲", ("父亲", "母亲", "父母", "子女", "孩子", "兄弟", "姐妹", "六亲", "亲人", "丧")),
    ("流年运势", ("流年", "运势", "大运", "运程")),
]

_PROVINCES = (
    "北京市", "天津市", "上海市", "重庆市",
    "河北省", "山西省", "辽宁省", "吉林省", "黑龙江省", "江苏省", "浙江省",
    "安徽省", "福建省", "江西省", "山东省", "河南省", "湖北省", "湖南省",
    "广东省", "海南省", "四川省", "贵州省", "云南省", "陕西省", "甘肃省",
    "青海省", "台湾省",
    "内蒙古自治区", "广西壮族自治区", "西藏自治区", "宁夏回族自治区",
    "新疆维吾尔自治区", "香港特别行政区", "澳门特别行政区",
)
_PROVINCE_SHORT = {
    "北京": "北京市", "天津": "天津市", "上海": "上海市", "重庆": "重庆市",
    "内蒙古": "内蒙古自治区", "广西": "广西壮族自治区", "西藏": "西藏自治区",
    "宁夏": "宁夏回族自治区", "新疆": "新疆维吾尔自治区",
    "香港": "香港特别行政区", "澳门": "澳门特别行政区",
}

_STATUS_TAGS = {"【已核实】": "已核实", "【已证伪】": "已证伪", "【未核实】": "未核实"}

_GZ_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def _categorize_all(text: str) -> list[str]:
    return [cat for cat, keywords in CATEGORIES if any(k in text for k in keywords)]


def _categorize(text: str) -> str:
    cats = _categorize_all(text)
    return cats[0] if cats else "其他"


def _province_of(birthplace: str) -> str | None:
    """地域脱敏：省级；识别不出省级则舍弃（宁缺毋滥）。"""
    for p in _PROVINCES:
        if p in birthplace:
            return p
    for short, full in _PROVINCE_SHORT.items():
        if birthplace.startswith(short):
            return full
    m = re.match(r"^(.{2,6}?省)", birthplace)
    return m.group(1) if m else None


def _city_of(birthplace: str) -> str | None:
    """地域脱敏：城市级（地级市/州/盟；直辖市即省级本身）。识别不出则舍弃。"""
    province = _province_of(birthplace)
    if province in ("北京市", "天津市", "上海市", "重庆市",
                    "香港特别行政区", "澳门特别行政区"):
        return province
    rest = birthplace
    if province and rest.startswith(province):
        rest = rest[len(province):]
    m = re.match(r"^(.{2,10}?(?:市|州|盟))", rest)
    return m.group(1) if m else None


def _sanitize_note(text: str, name: str) -> str:
    """事件简介脱敏：姓名、身份证/电话、详细住址（小区/门牌/街道号）一律删除；
    城市级地名保留（规则蒸馏要用方位信息）。"""
    t = text
    if name and name not in PLACEHOLDERS:
        t = t.replace(name, "命主")
    t = re.sub(r"\d{17}[\dXx]", "（已删）", t)                     # 身份证
    t = re.sub(r"1[3-9]\d{9}", "（已删）", t)                       # 手机号
    t = re.sub(r"\d{3,4}-\d{7,8}", "（已删）", t)                   # 座机号
    t = re.sub(r"[^\s，。；：、（）]*(?:小区|公寓|花园|山庄|新村|苑|大院)"
               r"[^\s，。；：、（）]*", "（已删）", t)              # 小区/楼盘名
    t = re.sub(r"\d+\s*(?:号楼|栋|单元|室|号院|层|户)", "（已删）", t)  # 楼栋门牌
    t = re.sub(r"(?:街|路|巷|大道|道)\s*\d+\s*号(?:\s*\d+\s*室)?",
               "（已删）", t)                                       # 街道号
    return t.strip()


def _strip_tags(text: str) -> str:
    for tag in _STATUS_TAGS:
        text = text.replace(tag, "")
    return text.strip()


def _section_lines(body: str, heading: str) -> list[str]:
    """取档案正文某固定小节（SECTIONS 内）的行，到下一个固定小节或文末。"""
    lines = body.splitlines()
    bounds = {f"## {s}" for s in store.SECTIONS} - {f"## {heading}"}
    start = next((i for i, ln in enumerate(lines)
                  if ln.strip() == f"## {heading}"), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].strip() in bounds), len(lines))
    return lines[start + 1:end]


def _chart_section_lines(body: str, heading: str, nxt: str) -> list[str]:
    """取「盘面」内嵌命盘 Markdown 的小节（如 ## 大运 到 ## 小运）。"""
    lines = body.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.strip() == f"## {heading}"), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].strip() == f"## {nxt}"), len(lines))
    return lines[start + 1:end]


def _parse_luck(body: str) -> list[dict]:
    luck = []
    for ln in _chart_section_lines(body, "大运", "小运"):
        m = re.match(r"^-\s*第\s*(\d+)\s*步：(\S{2})（[^）]*，(\d{4})\s*年）", ln.strip())
        if m:
            luck.append({"seq": int(m.group(1)), "pillar": m.group(2),
                         "start_year": int(m.group(3))})
    return luck


def _parse_focus(body: str) -> list[str]:
    cats: list[str] = []
    for ln in _section_lines(body, "主要关注方向"):
        t = ln.strip().lstrip("-•· ").strip()
        if not t or t in PLACEHOLDERS:
            continue
        for cat in _categorize_all(t):
            if cat not in cats:
                cats.append(cat)
    return cats


def _status_of(t: str) -> str:
    for tag, name in _STATUS_TAGS.items():
        if tag in t:
            return name
    return "未核实"


def _parse_feedback(body: str, name: str) -> list[dict]:
    """反馈事件：年份、类目、核实状态 + 事件简介（note，脱敏后；无实质内容则为 None）。"""
    events = []
    for ln in _section_lines(body, "反馈与澄清"):
        t = ln.strip().lstrip("-•· ").strip()
        if not t or t in PLACEHOLDERS:
            continue
        m = _YEAR_RE.search(t)
        note = _sanitize_note(_strip_tags(t), name)
        events.append({"year": int(m.group(0)) if m else None,
                       "category": _categorize(t),
                       "status": _status_of(t),
                       "note": note or None})
    return events


def _parse_events(body: str, name: str) -> list[dict]:
    """流年大事：年份（区间取首年）、干支、标签、核实状态 + 事件简介（脱敏后）。

    行形如「- 2016（丙申·交运年，入丁酉运）：【已核实】离乡，自四川乐山赴厦门读大学。」；
    无括号标签或缺事件内容时对应字段为 None（如实反映，不挡导出）。
    """
    events = []
    for ln in _section_lines(body, "流年大事"):
        t = ln.strip().lstrip("-•· ").strip()
        if not t or t in PLACEHOLDERS:
            continue
        m = re.match(r"^((?:19|20)\d{2})(?:[–—\-]\d{2,4})?"
                     r"(?:（([^）]*)）)?\s*[：:]\s*(.+)$", t)
        if m:
            year = int(m.group(1))
            label = m.group(2) or None
            note = m.group(3)
        else:
            ym = _YEAR_RE.search(t)
            year = int(ym.group(0)) if ym else None
            label = None
            note = t
        ganzhi = None
        if label:
            gz = _GZ_RE.search(label)
            ganzhi = gz.group(0) if gz else None
        note = _sanitize_note(_strip_tags(note), name)
        events.append({"year": year, "ganzhi": ganzhi, "label": label,
                       "note": note or None, "status": _status_of(t),
                       "category": _categorize(t)})
    return events


def chart_hash(pillars: list[str], birthplace: str) -> str:
    raw = f"{''.join(pillars)}|{birthplace.strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def build_package(meta: dict, body: str) -> tuple[dict, list[str]]:
    """组装脱敏包；返回 (package, 缺失项列表)。

    保证不含姓名、出生分钟/钟表时间、区县及以下地域；事件简介中城市级地名保留，
    直接定位信息（详细住址、证件、电话）已删除。
    """
    pillars = meta.get("pillars", [])
    if isinstance(pillars, str):
        pillars = pillars.split()
    pillars = [str(p) for p in pillars]
    birthplace = str(meta.get("birthplace", ""))
    gender = str(meta.get("gender", ""))
    name = str(meta.get("name", ""))

    pkg: dict = {"schema": SCHEMA,
                 "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "chart_hash": chart_hash(pillars, birthplace),
                 "gender": gender or None,
                 "pillars": pillars,
                 "luck_pillars": _parse_luck(body),
                 "focus_categories": _parse_focus(body),
                 "events": _parse_events(body, name),
                 "feedback": _parse_feedback(body, name)}

    # 出生信息脱敏：只保留年月日与时辰（时支），不留分钟与钟表时间
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(meta.get("birth_clock", "")).strip())
    if m:
        pkg["birth_date"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    if len(pillars) == 4 and len(pillars[3]) == 2:
        pkg["birth_shichen"] = pillars[3][1]
    province = _province_of(birthplace)
    if province:
        pkg["region_province"] = province
    city = _city_of(birthplace)
    if city:
        pkg["region_city"] = city

    missing = []
    if not gender:
        missing.append("性别")
    if len(pillars) != 4:
        missing.append("四柱")
    if not pkg["luck_pillars"]:
        missing.append("大运序列")
    if not pkg["feedback"]:
        missing.append("反馈事件（至少一条，任意核实状态）")
    return pkg, missing


def _find_archive(args) -> Path | None:
    if args.archive:
        p = Path(args.archive).expanduser().resolve()
        return p if p.is_file() else None
    root = store.resolve_root(args.memory_root, __file__)
    for path in store.iter_archives(root):
        meta, _ = store.parse_frontmatter(path.read_text(encoding="utf-8"))
        if meta and store.matches(meta, name=args.name, birth=args.birth,
                                  place=args.place, gender=args.gender,
                                  pillars=args.pillars):
            return path
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="share_export.py",
        description="从 memory 档案导出结构化脱敏包（JSON）到 share/pending/；不含姓名、分钟、区县及以下地域")
    ap.add_argument("--archive", default=None, help="档案文件路径（直接指定）")
    ap.add_argument("--name", default=None, help="姓名（检索条件）")
    ap.add_argument("--gender", default=None, choices=["男", "女"], help="性别（检索条件）")
    ap.add_argument("--birth", default=None,
                    help='出生时刻，格式 "YYYY-MM-DD HH:MM"（检索条件）')
    ap.add_argument("--place", default=None, help="出生地（检索条件）")
    ap.add_argument("--pillars", default=None,
                    help='四柱干支，如 "丁亥 乙巳 庚子 辛巳"（检索条件）')
    ap.add_argument("--memory-root", default=None,
                    help=f"档案根目录（默认技能根 memory/；亦可用环境变量 {store.ENV_VAR}）")
    ap.add_argument("--share-root", default=None,
                    help="share/ 目录（默认技能根 share/，测试覆盖用）")
    a = ap.parse_args()

    if not a.archive and all(v is None for v in (a.name, a.gender, a.birth,
                                                 a.place, a.pillars)):
        print("ERROR: 给 --archive <档案路径>，或至少一个检索条件"
              "（--name/--birth/--place/--gender/--pillars）。", file=sys.stderr)
        return 2

    try:
        arch = _find_archive(a)
        if arch is None:
            print("ERROR: 未找到匹配档案（先用 scripts/memory_save.py 建档，"
                  "并确认检索条件与档案一致）。", file=sys.stderr)
            return 2
        meta, body = store.parse_frontmatter(arch.read_text(encoding="utf-8"))
        pkg, missing = build_package(meta, body)
        if missing:
            print(f"ERROR: 档案完整度不足，拒绝导出。缺：{'、'.join(missing)}。"
                  f"（性别/四柱/大运齐全 + 至少一条反馈事件才可导出）", file=sys.stderr)
            return 2

        share_root = (Path(a.share_root).expanduser().resolve() if a.share_root
                      else Path(__file__).resolve().parents[1] / "share")
        pending = share_root / "pending"
        pending.mkdir(parents=True, exist_ok=True)
        out = pending / f"{pkg['chart_hash']}.json"
        # 换盘孤儿包提示：pending 中同出生日、同性别但盘 hash 不同的旧包，
        # 多为换盘/信息更正后的残留，提醒人工清理（只提示，不自动删）
        for old in sorted(pending.glob("*.json")):
            if old.name == out.name:
                continue
            try:
                opkg = json.loads(old.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (opkg.get("birth_date") == pkg.get("birth_date")
                    and opkg.get("gender") == pkg.get("gender")
                    and opkg.get("chart_hash") != pkg["chart_hash"]):
                print(f"WARN: pending 中已有同出生日同性别的旧包（盘 hash 不同），"
                      f"疑似换盘残留：{old}；确认后请手动删除，避免误推。",
                      file=sys.stderr)
        out.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(out)
        return 0
    except SystemExit:
        raise
    except Exception:
        print("ERROR: 导出内部错误。", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
