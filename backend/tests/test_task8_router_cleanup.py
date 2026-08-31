"""Task 8：旧路由清理与统一入口约束。"""
from __future__ import annotations

import asyncio

from backend.agents.router import QuestionRouter
from backend.config import Settings


def test_legacy_router_config_is_removed() -> None:
    assert "agent_router_mode" not in Settings.model_fields
    assert "AGENT_ROUTER_MODE" not in {
        str(field.alias) for field in Settings.model_fields.values()
    }


def test_legacy_async_route_delegates_to_query_planner() -> None:
    plan = asyncio.run(QuestionRouter().route("广州今天天气"))

    assert plan.router_source == "planner"
    assert plan.primary.tool == "weather_search"


def test_legacy_adapter_keeps_offline_rule_baseline() -> None:
    plan = QuestionRouter().route_rule("缓考申请表下载")

    assert plan.router_source == "rule"
    assert plan.primary.tool == "download_search"
