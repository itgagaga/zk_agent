"""QuestionRouter 单元测试（不依赖 LLM API）。"""
from __future__ import annotations

import unittest

from backend.agents.router import QuestionRouter


class QuestionRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = QuestionRouter()
        self.router.mode = "rule"

    def test_rule_route_weather(self) -> None:
        plan = self.router.route_rule("广州今天天气")
        self.assertEqual(plan.primary.intent_label, "天气查询")
        self.assertEqual(plan.primary.tool, "weather_search")

    def test_rule_route_general_when_no_keyword(self) -> None:
        plan = self.router.route_rule("介绍一下仲恺农业工程学院的历史")
        self.assertEqual(plan.primary.intent_label, "通用问答")
        self.assertEqual(plan.primary.path, "general_rag")

    def test_hybrid_confident_single_tool(self) -> None:
        self.assertTrue(
            QuestionRouter._is_confident_rule_match(
                "缓考申请表下载",
                self.router._match_all_intents("缓考申请表下载"),
            )
        )

    def test_hybrid_not_confident_without_match(self) -> None:
        question = "外面现在什么情况"
        self.assertFalse(
            QuestionRouter._is_confident_rule_match(
                question,
                self.router._match_all_intents(question),
            )
        )

    def test_hybrid_not_confident_ambiguous_multi_match(self) -> None:
        question = "缓考申请表在哪里下载，联系电话是多少"
        matched = self.router._match_all_intents(question)
        self.assertGreaterEqual(len(matched), 2)
        self.assertFalse(QuestionRouter._is_confident_rule_match(question, matched))

    def test_collab_affair_process(self) -> None:
        plan = self.router.route_rule("缓考怎么申请，需要哪些材料")
        self.assertEqual(plan.mode, "collab")
        self.assertIn("download_search", {i.tool for i in plan.intents if i.tool})


if __name__ == "__main__":
    unittest.main()
