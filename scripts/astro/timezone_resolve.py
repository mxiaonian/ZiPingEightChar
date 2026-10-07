"""
timezone_resolve.py — 把「当地钟表时间 + 地点」解析为 UTC。

诚实声明（近似性）
==================
1949 年以前中国的「民国五时区」在执行层面存在大量地方差异：各省、
各县乃至铁路、电报系统采用的标准时并不完全统一，本模块内嵌的
「年份 × 省份 → UTC 偏移」表是按 1919 年中央观象台五时区方案
（及后来的内政部修订）整理的**省级粒度近似**，与个别地方的实际
执行可能有数十分钟乃至一小时量级的出入。昆仑/新藏时区的分界
（82.5°E）在省级粒度无法表达，本表仅以少数西部城市的伪省份键
（「新疆西部」「西藏西部」）粗略体现。调用方应保留 audit 中的
source / tz_used，供人工复核边界情形。
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# 民国五时区（1912-01-01 ~ 1949-09-30）：省份 → UTC 偏移（分钟）
# ---------------------------------------------------------------------------
# 昆仑时区  82.5°E  UTC+5:30  新疆西部、西藏西部（省级粒度无法表达，见伪键）
# 新藏时区  90°E    UTC+6     新疆东部、西藏东部
# 陇蜀时区  105°E   UTC+7     陕西/甘肃/宁夏/四川/重庆/云南/贵州/青海大部
# 中原时区  120°E   UTC+8     华东/华中/华北/华南大部
# 长白时区  127.5°E UTC+8:30  黑龙江/吉林
PROVINCE_OFFSET_MIN: dict[str, int] = {
    # 新藏时区
    "新疆": 360,
    "西藏": 360,
    # 昆仑时区（伪省份键，仅由城市表命中；省级粒度下新疆/西藏整体归入新藏时区）
    "新疆西部": 330,
    "西藏西部": 330,
    # 陇蜀时区；西康（已撤销，今川西藏东）归此
    "陕西": 420,
    "甘肃": 420,
    "宁夏": 420,
    "四川": 420,
    "重庆": 420,
    "云南": 420,
    "贵州": 420,
    "青海": 420,
    "西康": 420,
    # 长白时区。辽宁历史上处于长白时区西缘（亦有资料归中原），
    # 本表取 +510；与 +480 之差为半小时，属本表近似范围
    "辽宁": 510,
    "吉林": 510,
    "黑龙江": 510,
    # 中原标准时区。历史省份热河/察哈尔/绥远并入华北→中原；
    # 内蒙古横跨甚广（西部实为陇蜀边缘），此处整体取中原，属近似
    "北京": 480,
    "天津": 480,
    "河北": 480,
    "山西": 480,
    "内蒙古": 480,
    "热河": 480,
    "察哈尔": 480,
    "绥远": 480,
    "上海": 480,
    "江苏": 480,
    "浙江": 480,
    "安徽": 480,
    "福建": 480,
    "江西": 480,
    "山东": 480,
    "河南": 480,
    "湖北": 480,
    "湖南": 480,
    "广东": 480,
    "广西": 480,
    "海南": 480,
    "台湾": 480,
    "香港": 480,
    "澳门": 480,
}

_ZONE_NAME = {
    330: "昆仑时区",
    360: "新藏时区",
    420: "陇蜀时区",
    480: "中原标准时区",
    510: "长白时区",
}

_PSEUDO_PROVINCES = frozenset({"新疆西部", "西藏西部"})

# 城市名 → 省份（简表：省会及主要地级市；Location.name 常为城市名）
_CITY_TABLE: dict[str, tuple[str, ...]] = {
    "河北": ("石家庄", "唐山", "秦皇岛", "邯郸", "邢台", "保定", "张家口",
             "承德", "沧州", "廊坊", "衡水"),
    "山西": ("太原", "大同", "阳泉", "长治", "晋城", "朔州", "晋中",
             "运城", "忻州", "临汾", "吕梁"),
    "内蒙古": ("呼和浩特", "包头", "乌海", "赤峰", "通辽", "鄂尔多斯",
               "呼伦贝尔", "巴彦淖尔", "乌兰察布", "锡林郭勒", "阿拉善", "兴安"),
    "辽宁": ("沈阳", "大连", "鞍山", "抚顺", "本溪", "丹东", "锦州",
             "营口", "阜新", "辽阳", "盘锦", "铁岭", "朝阳", "葫芦岛"),
    "吉林": ("长春", "吉林", "四平", "辽源", "通化", "白山", "松原",
             "白城", "延边"),
    "黑龙江": ("哈尔滨", "齐齐哈尔", "鸡西", "鹤岗", "双鸭山", "大庆",
               "伊春", "佳木斯", "七台河", "牡丹江", "黑河", "绥化", "大兴安岭"),
    "江苏": ("南京", "无锡", "徐州", "常州", "苏州", "南通", "连云港",
             "淮安", "盐城", "扬州", "镇江", "泰州", "宿迁"),
    "浙江": ("杭州", "宁波", "温州", "嘉兴", "湖州", "绍兴", "金华",
             "衢州", "舟山", "台州", "丽水"),
    "安徽": ("合肥", "芜湖", "蚌埠", "淮南", "马鞍山", "淮北", "铜陵",
             "安庆", "黄山", "滁州", "阜阳", "宿州", "六安", "亳州",
             "池州", "宣城"),
    "福建": ("福州", "厦门", "莆田", "三明", "泉州", "漳州", "南平",
             "龙岩", "宁德"),
    "江西": ("南昌", "景德镇", "萍乡", "九江", "新余", "鹰潭", "赣州",
             "吉安", "宜春", "抚州", "上饶"),
    "山东": ("济南", "青岛", "淄博", "枣庄", "东营", "烟台", "潍坊",
             "济宁", "泰安", "威海", "日照", "临沂", "德州", "聊城",
             "滨州", "菏泽", "莱芜"),
    "河南": ("郑州", "开封", "洛阳", "平顶山", "安阳", "鹤壁", "新乡",
             "焦作", "濮阳", "许昌", "漯河", "三门峡", "南阳", "商丘",
             "信阳", "周口", "驻马店", "济源"),
    "湖北": ("武汉", "黄石", "十堰", "宜昌", "襄阳", "鄂州", "荆门",
             "孝感", "荆州", "黄冈", "咸宁", "随州", "恩施", "仙桃",
             "潜江", "天门"),
    "湖南": ("长沙", "株洲", "湘潭", "衡阳", "邵阳", "岳阳", "常德",
             "张家界", "益阳", "郴州", "永州", "怀化", "娄底", "湘西"),
    "广东": ("广州", "韶关", "深圳", "珠海", "汕头", "佛山", "江门",
             "湛江", "茂名", "肇庆", "惠州", "梅州", "汕尾", "河源",
             "阳江", "清远", "东莞", "中山", "潮州", "揭阳", "云浮"),
    "广西": ("南宁", "柳州", "桂林", "梧州", "北海", "防城港", "钦州",
             "贵港", "玉林", "百色", "贺州", "河池", "来宾", "崇左"),
    "海南": ("海口", "三亚", "三沙", "儋州"),
    "四川": ("成都", "自贡", "攀枝花", "泸州", "德阳", "绵阳", "广元",
             "遂宁", "内江", "乐山", "南充", "眉山", "宜宾", "广安",
             "达州", "雅安", "巴中", "资阳", "阿坝", "甘孜", "凉山"),
    "贵州": ("贵阳", "六盘水", "遵义", "安顺", "毕节", "铜仁",
             "黔西南", "黔东南", "黔南"),
    "云南": ("昆明", "曲靖", "玉溪", "保山", "昭通", "丽江", "普洱",
             "临沧", "楚雄", "红河", "文山", "西双版纳", "大理", "德宏",
             "怒江", "迪庆"),
    "西藏": ("拉萨", "日喀则", "昌都", "林芝", "山南", "那曲"),
    "西藏西部": ("阿里",),
    "陕西": ("西安", "铜川", "宝鸡", "咸阳", "渭南", "延安", "汉中",
             "榆林", "安康", "商洛"),
    "甘肃": ("兰州", "嘉峪关", "金昌", "白银", "天水", "武威", "张掖",
             "平凉", "酒泉", "庆阳", "定西", "陇南", "临夏", "甘南", "敦煌"),
    "青海": ("西宁", "海东", "海北", "黄南", "果洛", "玉树", "海西", "海南州"),
    "宁夏": ("银川", "石嘴山", "吴忠", "固原", "中卫"),
    "新疆": ("乌鲁木齐", "克拉玛依", "吐鲁番", "哈密", "昌吉", "博尔塔拉",
             "巴音郭楞", "库尔勒", "伊犁", "塔城", "阿勒泰", "石河子",
             "奎屯", "阿拉尔", "五家渠"),
    # 昆仑时区（82.5°E）大致覆盖：喀什噶尔、和阗一带
    "新疆西部": ("喀什", "和田", "克孜勒苏", "阿克苏", "阿图什",
                 "图木舒克", "莎车", "叶城"),
    "台湾": ("台北", "高雄", "台中", "台南", "基隆", "新竹", "嘉义", "桃园"),
}

CITY_TO_PROVINCE: dict[str, str] = {
    city: prov for prov, cities in _CITY_TABLE.items() for city in cities
}

_NAME_TO_PROVINCE: dict[str, str] = {
    **{p: p for p in PROVINCE_OFFSET_MIN if p not in _PSEUDO_PROVINCES},
    **CITY_TO_PROVINCE,
}

_PREFIX_KEYS = sorted(_NAME_TO_PROVINCE, key=len, reverse=True)

_ADMIN_SUFFIXES = (
    "维吾尔自治区", "壮族自治区", "回族自治区", "特别行政区",
    "自治区", "省", "市", "地区", "州", "盟", "县", "区",
)

# 1986–1991 全国夏令时期间未实行夏令时的省份（官方仍用 UTC+8 北京时间；
# tzdata 的 Asia/Urumqi 条目同样不含 DST 规则，可相互印证）
_DST_EXEMPT_PROVINCES = frozenset({"新疆"})

_HIST_START = datetime(1912, 1, 1)
_HIST_END = datetime(1949, 10, 1)  # 自此起回退 zoneinfo（Asia/Shanghai，含 1986–1991 DST）


def _strip_admin_suffix(name: str) -> str:
    for suffix in _ADMIN_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def _resolve_province(name: str) -> str | None:
    """从 Location.name 提取省份键；name 可能是省名或城市名，匹配不到返回 None。"""
    key = (name or "").strip()
    if not key:
        return None
    if key in _NAME_TO_PROVINCE:
        return _NAME_TO_PROVINCE[key]
    stripped = _strip_admin_suffix(key)
    if stripped in _NAME_TO_PROVINCE:
        return _NAME_TO_PROVINCE[stripped]
    # 前缀匹配，如「甘肃省兰州市」「新疆乌鲁木齐」
    for cand in _PREFIX_KEYS:
        if key.startswith(cand):
            return _NAME_TO_PROVINCE[cand]
    return None


def historical_offset_minutes(dt_naive: datetime, province: str) -> int | None:
    """
    若自维护表覆盖该 (年份, 省份)，返回 UTC 偏移（分钟）。
    否则返回 None，由调用方回退到 zoneinfo。

    覆盖区间：1912-01-01 ~ 1949-09-30（民国五时区）。
    1912 年之前返回 None（zoneinfo 给 LMT，符合历史实况）；
    1949-10-01 起返回 None（全国统一北京时间，zoneinfo 正确处理 1986–1991 DST）。
    """
    if not province or dt_naive < _HIST_START or dt_naive >= _HIST_END:
        return None
    key = province.strip()
    return PROVINCE_OFFSET_MIN.get(key) or PROVINCE_OFFSET_MIN.get(
        _strip_admin_suffix(key)
    )


def _fmt_offset(minutes: int) -> str:
    sign = "+" if minutes >= 0 else "-"
    m = abs(minutes)
    return f"UTC{sign}{m // 60:02d}:{m % 60:02d}"


def to_utc(local_dt_naive: datetime, loc) -> tuple[datetime, dict]:
    """
    返回 (UTC datetime, audit_info)。
    audit_info 固定键：tz_used(str)、is_dst(bool)、dst_offset_min(int)、source(str)。
    """
    province = _resolve_province(getattr(loc, "name", ""))
    offset = historical_offset_minutes(local_dt_naive, province)

    if offset is not None:
        utc = (local_dt_naive - timedelta(minutes=offset)).replace(
            tzinfo=timezone.utc
        )
        return utc, {
            "tz_used": f"{_ZONE_NAME[offset]}({_fmt_offset(offset)})",
            "is_dst": False,
            "dst_offset_min": 0,
            "source": "historical_table",
        }

    tz_name = getattr(loc, "tz", None) or "Asia/Shanghai"
    tz = ZoneInfo(tz_name)
    localized = local_dt_naive.replace(tzinfo=tz)
    dst = localized.dst()
    is_dst = bool(dst) and dst != timedelta(0)
    dst_min = int(dst.total_seconds() // 60) if is_dst else 0

    if is_dst and province in _DST_EXEMPT_PROVINCES:
        # 退回标准时（UTC+8）：直接按「标准偏移」换算，保持 naive 不变
        std_offset = localized.utcoffset() - dst
        utc = (local_dt_naive - std_offset).replace(tzinfo=timezone.utc)
        return utc, {
            "tz_used": tz_name,
            "is_dst": False,
            "dst_offset_min": 0,
            "source": "zoneinfo",
        }

    utc = localized.astimezone(timezone.utc)
    return utc, {
        "tz_used": tz_name,
        "is_dst": is_dst,
        "dst_offset_min": dst_min,
        "source": "zoneinfo",
    }
