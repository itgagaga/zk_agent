"""课表日期、动态教学周及历史周切换的回归测试。"""
import asyncio
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.api import schedule as schedule_api
from backend.services import schedule_parser, schedule_store


def saved_schedule():
    courses = [
        {
            "name": name,
            "day": "星期三",
            "start": "08:00",
            "week_ranges": ranges,
        }
        for name, ranges in [
            ("仅第一周", [[1, 1]]),
            ("仅第八周", [[8, 8]]),
            ("全学期", []),
        ]
    ]
    return {
        "meta": {"semester": "2026-2027-1"},
        "current_week": 1,  # 模拟上传后留在数据库中的过期周次。
        "courses": courses,
        "grid": [{"time_slot": "第一二节", "days": {"星期三": courses}}],
    }


class ScheduleCalendarTests(unittest.TestCase):
    def test_october_21_is_week_eight_with_correct_dates(self):
        week = schedule_parser.estimate_current_week("2026-2027-1", date(2026, 10, 21))
        self.assertEqual(week, 8)
        dates = schedule_parser.week_calendar_range("2026-2027-1", week)
        self.assertEqual(dates["星期一"], "10/19")
        self.assertEqual(dates["星期三"], "10/21")
        self.assertEqual(dates["星期日"], "10/25")

    def test_week_changes_on_monday_instead_of_nominal_start_weekday(self):
        for day, expected in [(date(2026, 9, 6), 1), (date(2026, 9, 7), 2)]:
            with self.subTest(day=day):
                self.assertEqual(schedule_parser.estimate_current_week("2026-2027-1", day), expected)

    def test_estimated_week_contains_today_throughout_both_terms(self):
        for semester in ["2026-2027-1", "2026-2027-2"]:
            start = schedule_parser.semester_week_start(semester)
            for offset in range(20 * 7):
                today = start + timedelta(days=offset)
                week = schedule_parser.estimate_current_week(semester, today)
                dates = schedule_parser.week_calendar_range(semester, week)
                with self.subTest(semester=semester, today=today):
                    self.assertEqual(
                        dates[schedule_parser.WEEKDAY_HEADERS[today.weekday()]],
                        today.strftime("%m/%d"),
                    )

    def test_before_semester_and_unknown_semester_fall_back_to_week_one(self):
        self.assertEqual(schedule_parser.estimate_current_week("2026-2027-1", date(2026, 8, 1)), 1)
        self.assertEqual(schedule_parser.estimate_current_week("", date(2026, 10, 21)), 1)
        self.assertEqual(schedule_parser.week_calendar_range("", 1), {})
        self.assertEqual(schedule_parser.week_calendar_range("2026-2027-1", 0), {})

    def test_campus_date_uses_beijing_timezone_at_utc_date_boundary(self):
        instant = datetime(2026, 10, 20, 16, 30, tzinfo=timezone.utc)
        with patch.object(schedule_parser, "datetime") as clock:
            clock.now.side_effect = lambda tz: instant.astimezone(tz)
            self.assertEqual(schedule_parser.campus_today(), date(2026, 10, 21))

    def test_today_courses_ignore_saved_week_and_filter_by_real_week(self):
        courses = schedule_parser.get_today_courses(saved_schedule(), date(2026, 10, 21))
        self.assertEqual([course["name"] for course in courses], ["仅第八周", "全学期"])
        self.assertTrue(all(course["active_week"] == 8 for course in courses))

    def test_explicit_course_week_is_still_supported(self):
        courses = schedule_parser.get_today_courses(saved_schedule(), date(2026, 10, 21), week=1)
        self.assertEqual([course["name"] for course in courses], ["仅第一周", "全学期"])


class ScheduleStoreTests(unittest.TestCase):
    def test_read_recomputes_week_without_modifying_persisted_schedule(self):
        row = SimpleNamespace(
            data=json.dumps(saved_schedule()), file_path="schedule.xls",
            filename="学生课表.xls", updated_at=None,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        with patch.object(schedule_parser, "campus_today", return_value=date(2026, 10, 21)):
            loaded = schedule_store.load_schedule_data(db, 1)
            self.assertEqual(loaded["current_week"], 8)
            self.assertEqual(loaded["_filename"], "学生课表.xls")
        with patch.object(schedule_parser, "campus_today", return_value=date(2026, 10, 26)):
            self.assertEqual(schedule_store.load_schedule_data(db, 1)["current_week"], 9)
        self.assertEqual(json.loads(row.data)["current_week"], 1)
        db.commit.assert_not_called()


class ScheduleApiTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=1)
        self.clock = patch.object(schedule_api, "campus_today", return_value=date(2026, 10, 21))
        self.store = patch.object(schedule_api, "load_schedule_data", return_value=saved_schedule())
        self.clock.start()
        self.store.start()
        self.addCleanup(self.clock.stop)
        self.addCleanup(self.store.stop)

    def week_response(self, week=None):
        response = asyncio.run(schedule_api.get_week_grid(week=week, current_user=self.user, db=None))
        return json.loads(response.body)

    def test_default_week_uses_today_even_with_stale_saved_week(self):
        response = self.week_response()
        self.assertEqual(response["current_week"], 8)
        self.assertEqual(response["selected_week"], 8)
        self.assertEqual(response["day_dates"]["星期三"], "10/21")
        self.assertTrue(response["is_current_week"])
        self.assertEqual(response["course_count"], 2)
        self.assertEqual(
            [course["name"] for course in response["grid"][0]["days"]["星期三"]],
            ["仅第八周", "全学期"],
        )

    def test_history_week_is_not_marked_as_this_week(self):
        response = self.week_response(1)
        self.assertEqual(response["selected_week"], 1)
        self.assertEqual(response["current_week"], 8)
        self.assertEqual(response["day_dates"]["星期三"], "09/02")
        self.assertFalse(response["is_current_week"])
        self.assertEqual([c["name"] for c in response["week_courses"]], ["仅第一周", "全学期"])

    def test_week_selection_stays_within_bounds(self):
        self.assertEqual(self.week_response(0)["selected_week"], 1)
        response = self.week_response(100)
        self.assertEqual(response["selected_week"], response["max_week"])

    def test_today_api_and_advice_use_the_same_real_week(self):
        with (
            patch.object(schedule_api, "_get_weather", new_callable=AsyncMock, return_value=(None, False)),
            patch.object(schedule_api, "_get_advice", new_callable=AsyncMock, return_value=("建议", False)) as advice,
        ):
            response = asyncio.run(schedule_api.get_today_campus(
                refresh_advice=False, current_user=self.user, db=None,
            ))
        self.assertEqual(response.current_week, 8)
        self.assertEqual(response.weekday, "星期三")
        self.assertEqual([c["name"] for c in response.today_courses], ["仅第八周", "全学期"])
        self.assertEqual(advice.await_args.kwargs["week"], 8)
        self.assertEqual(advice.await_args.kwargs["courses"], response.today_courses)

    def test_profile_reports_recomputed_week(self):
        # 通过真实读取路径验证个人课表页也不会继续显示上传时的周次。
        row = SimpleNamespace(data=json.dumps(saved_schedule()), file_path=None, filename=None, updated_at=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        with (
            patch.object(schedule_api, "load_schedule_data", side_effect=schedule_store.load_schedule_data),
            patch.object(schedule_parser, "campus_today", return_value=date(2026, 10, 21)),
        ):
            response = asyncio.run(schedule_api.get_schedule_profile(current_user=self.user, db=db))
        self.assertEqual(response.schedule["current_week"], 8)


if __name__ == "__main__":
    unittest.main()
