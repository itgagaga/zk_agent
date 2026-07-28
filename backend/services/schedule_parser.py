"""仲恺教务系统导出的学生个人课表 Excel 解析。"""
from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO
from typing import Any

import pandas as pd

WEEKDAY_HEADERS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
WEEKDAY_INDEX = {name: i for i, name in enumerate(WEEKDAY_HEADERS)}

TIME_SLOT_META: dict[str, dict[str, str]] = {
    "第一二节": {"start": "08:00", "end": "09:40", "label": "第 1–2 节"},
    "第三四节": {"start": "10:00", "end": "11:40", "label": "第 3–4 节"},
    "第五节": {"start": "14:00", "end": "14:40", "label": "第 5 节"},
    "第六七节": {"start": "15:00", "end": "16:40", "label": "第 6–7 节"},
    "第八九节": {"start": "17:00", "end": "18:40", "label": "第 8–9 节"},
    "第十十一十二节": {"start": "19:00", "end": "21:25", "label": "第 10–12 节"},
}

WEEKS_RE = re.compile(
    r"(?P<weeks>[\d,\-]+)?(?:\(\[?周\]?\))?\[(?P<periods>\d+(?:-\d+)?)节\]"
)
META_RE = re.compile(
    r"学年学期[：:]\s*(?P<semester>[\d\-]+)\s+"
    r"班级[：:]\s*(?P<klass>[^\s]+)\s+"
    r"专业[：:]\s*(?P<major>[^\s]+)\s+"
    r"院系[：:]\s*(?P<department>[^\s]+)"
    r"(?:\s+打印日期[：:]\s*(?P<print_date>[\d\-]+))?"
)


def _clean(text: Any) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    return str(text).strip()


def _parse_week_ranges(weeks_str: str) -> list[tuple[int, int]]:
    """将 '1-4,7-8,10' 解析为 [(1,4), (7,8), (10,10)]。"""
    ranges: list[tuple[int, int]] = []
    for part in weeks_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            ranges.append((int(a), int(b)))
        else:
            n = int(part)
            ranges.append((n, n))
    return ranges


def week_in_ranges(week: int, ranges: list[tuple[int, int]]) -> bool:
    return any(lo <= week <= hi for lo, hi in ranges)


def estimate_current_week(semester: str, today: date | None = None) -> int:
    """根据学年学期估算当前教学周（1 起）。"""
    today = today or date.today()
    m = re.match(r"(\d{4})-(\d{4})-(\d)", semester.strip())
    if not m:
        return 1
    y1, y2, term = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if term == 1:
        start = date(y1, 9, 1)
    else:
        start = date(y2, 2, 24)
    delta = (today - start).days
    if delta < 0:
        return 1
    return delta // 7 + 1


def _parse_course_block(block: str) -> dict[str, Any] | None:
    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
    if len(lines) < 2:
        return None

    name = lines[0]
    teacher = lines[1]
    weeks_str = ""
    periods = ""
    location = ""

    for ln in lines[2:]:
        wm = WEEKS_RE.search(ln)
        if wm:
            weeks_str = wm.group("weeks") or ""
            periods = wm.group("periods") or ""
        elif not location:
            location = ln
        else:
            location = f"{location} {ln}"

    week_ranges = _parse_week_ranges(weeks_str) if weeks_str else []
    return {
        "name": name,
        "teacher": teacher,
        "weeks": weeks_str,
        "week_ranges": week_ranges,
        "periods": periods,
        "location": location,
        "is_online": "网络" in location or "虚拟教室" in location,
    }


def _split_cell_courses(cell: str) -> list[dict[str, Any]]:
    cell = cell.strip()
    if not cell:
        return []
    blocks = re.split(r"\n\s*\n", cell)
    courses: list[dict[str, Any]] = []
    for block in blocks:
        parsed = _parse_course_block(block.strip())
        if parsed:
            courses.append(parsed)
    return courses


def parse_schedule_excel(content: bytes, filename: str = "") -> dict[str, Any]:
    """解析 .xls / .xlsx 课表，返回结构化 JSON。"""
    buf = BytesIO(content)
    suffix = filename.lower().rsplit(".", 1)[-1] if filename else "xls"
    engine = "xlrd" if suffix == "xls" else "openpyxl"
    df = pd.read_excel(buf, header=None, engine=engine)

    title = _clean(df.iloc[0, 0]) if len(df) > 0 else ""
    meta_line = _clean(df.iloc[1, 0]) if len(df) > 1 else ""
    meta_match = META_RE.search(meta_line.replace("\n", " "))
    meta = {
        "title": title,
        "semester": meta_match.group("semester") if meta_match else "",
        "class_name": meta_match.group("klass") if meta_match else "",
        "major": meta_match.group("major") if meta_match else "",
        "department": meta_match.group("department") if meta_match else "",
        "print_date": meta_match.group("print_date") if meta_match else "",
        "raw_meta": meta_line,
    }

    grid: list[dict[str, Any]] = []
    courses: list[dict[str, Any]] = []

    for row_idx in range(3, len(df)):
        slot_label = _clean(df.iloc[row_idx, 0])
        if not slot_label or slot_label not in TIME_SLOT_META:
            continue
        slot_meta = TIME_SLOT_META[slot_label]
        row_entry: dict[str, Any] = {
            "time_slot": slot_label,
            "start": slot_meta["start"],
            "end": slot_meta["end"],
            "label": slot_meta["label"],
            "days": {},
        }
        for col_idx, day_name in enumerate(WEEKDAY_HEADERS, start=1):
            if col_idx >= df.shape[1]:
                break
            cell = _clean(df.iloc[row_idx, col_idx])
            day_courses = _split_cell_courses(cell)
            if day_courses:
                row_entry["days"][day_name] = day_courses
                for c in day_courses:
                    courses.append(
                        {
                            **c,
                            "day": day_name,
                            "day_index": WEEKDAY_INDEX[day_name],
                            "time_slot": slot_label,
                            "start": slot_meta["start"],
                            "end": slot_meta["end"],
                        }
                    )
        grid.append(row_entry)

    current_week = estimate_current_week(meta.get("semester", ""))
    return {
        "meta": meta,
        "grid": grid,
        "courses": courses,
        "current_week": current_week,
        "parsed_at": datetime.utcnow().isoformat() + "Z",
    }


def get_today_courses(
    schedule: dict[str, Any],
    today: date | None = None,
    *,
    week: int | None = None,
) -> list[dict[str, Any]]:
    """筛选指定日、指定教学周应上的课程。"""
    today = today or date.today()
    weekday = today.weekday()  # 0=Mon
    day_name = WEEKDAY_HEADERS[weekday]
    if week is None:
        week = schedule.get("current_week") or estimate_current_week(
            schedule.get("meta", {}).get("semester", ""), today
        )

    result: list[dict[str, Any]] = []
    for course in schedule.get("courses", []):
        if course.get("day") != day_name:
            continue
        ranges = course.get("week_ranges") or []
        if ranges and not week_in_ranges(week, ranges):
            continue
        result.append({**course, "active_week": week})

    result.sort(key=lambda c: c.get("start", ""))
    return result


def get_semester_week_bounds(courses: list[dict[str, Any]]) -> tuple[int, int]:
    """从课程周次推断学期教学周范围。"""
    max_week = 18
    for course in courses:
        for lo, hi in course.get("week_ranges") or []:
            max_week = max(max_week, hi)
    return 1, max(max_week, 20)


def semester_week_start(semester: str) -> date | None:
    m = re.match(r"(\d{4})-(\d{4})-(\d)", (semester or "").strip())
    if not m:
        return None
    y1, y2, term = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return date(y1, 9, 1) if term == 1 else date(y2, 2, 24)


def week_calendar_range(semester: str, week: int) -> dict[str, str]:
    """返回某教学周周一至周日的日期字符串。"""
    start = semester_week_start(semester)
    if not start or week < 1:
        return {}
    monday = start.fromordinal(start.toordinal() + (week - 1) * 7)
    # 对齐到周一
    monday = monday.fromordinal(monday.toordinal() - monday.weekday())
    days = {}
    for i, name in enumerate(WEEKDAY_HEADERS):
        d = monday.fromordinal(monday.toordinal() + i)
        days[name] = d.strftime("%m/%d")
    return days


def filter_courses_by_week(
    courses: list[dict[str, Any]], week: int
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for course in courses:
        ranges = course.get("week_ranges") or []
        if ranges and not week_in_ranges(week, ranges):
            continue
        result.append({**course, "active_week": week})
    return result


def filter_grid_by_week(
    grid: list[dict[str, Any]], week: int
) -> list[dict[str, Any]]:
    """按教学周过滤课表网格，仅保留当周有课的课程块。"""
    filtered: list[dict[str, Any]] = []
    for row in grid:
        days: dict[str, list[dict[str, Any]]] = {}
        for day_name, day_courses in (row.get("days") or {}).items():
            active = [
                {**c, "active_week": week}
                for c in day_courses
                if not c.get("week_ranges")
                or week_in_ranges(week, c.get("week_ranges") or [])
            ]
            if active:
                days[day_name] = active
        filtered.append({**row, "days": days})
    return filtered


def build_course_legend(courses: list[dict[str, Any]]) -> list[dict[str, str]]:
    """为当周课程生成稳定配色图例（按课程名去重排序）。"""
    names = sorted({c.get("name", "") for c in courses if c.get("name")})
    return [{"name": name, "color_index": i % 8} for i, name in enumerate(names)]
