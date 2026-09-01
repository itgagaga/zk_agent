from backend.rag.contracts import Evidence, EvidenceBundle, SubQuestion
from backend.rag.evidence_gate import EvidenceGate
from backend.rag.personal_evidence_policy import PersonalEvidencePolicy


def _doc(chunk_id, title, snippet, *, user=False, score=0.8):
    metadata = {"doc_id": chunk_id, "subquestion_id": "q1"}
    if user:
        metadata["user_id"] = 7
    return Evidence.from_rag_hit(
        {
            "chunk_id": chunk_id,
            "title": title,
            "snippet": snippet,
            "score": score,
            "metadata": metadata,
        },
        retriever="user_docs" if user else "campus_rag",
    )


def test_personal_curriculum_is_high_relevance_for_personal_course_question():
    personal = _doc(
        "personal-plan",
        "我的信息与计算科学培养方案",
        "大一课程包括高等数学、程序设计，培养方案列出课程学分和学期安排。",
        user=True,
    )
    public = _doc(
        "public-major",
        "信息与计算科学专业介绍",
        "专业培养目标和就业方向介绍。",
    )
    bundle = EvidenceBundle(
        query="根据我的信计培养方案安排大一课程和学分",
        evidences=[personal, public],
        retrievers=["user_docs", "campus_rag"],
        subquestions=[SubQuestion(
            id="q1",
            query="根据我的信计培养方案安排大一课程和学分",
            retrievers=["user_docs", "campus_rag"],
        )],
        diagnostics={"knowledge_scope": "with_personal"},
    )

    policy = PersonalEvidencePolicy()
    assessment = EvidenceGate().assess(bundle)
    relevance = policy.assess(bundle, assessment)

    assert relevance[0].level == "high"
    assert {"培养方案", "课程", "学分"}.issubset(relevance[0].matched_concepts)


def test_unrelated_personal_curriculum_is_excluded_from_weather_context():
    personal = _doc(
        "personal-plan",
        "我的信息与计算科学培养方案",
        "大一课程包括高等数学和程序设计。",
        user=True,
        score=0.99,
    )
    weather = Evidence.from_tool_item(
        {"title": "广州天气", "snippet": "今天晴，不需要带伞。", "score": 0.8},
        tool="weather_search",
    )
    weather.metadata["subquestion_id"] = "q1"
    bundle = EvidenceBundle(
        query="今天广州天气怎么样，要不要带伞",
        evidences=[personal, weather],
        retrievers=["user_docs", "weather_search"],
        subquestions=[SubQuestion(
            id="q1",
            query="今天广州天气怎么样，要不要带伞",
            retrievers=["user_docs", "weather_search"],
        )],
        diagnostics={"knowledge_scope": "with_personal"},
    )

    selected, relevance, _ = PersonalEvidencePolicy().select(bundle)

    assert relevance[0].level == "none"
    assert [item.retriever for item in selected] == ["weather_search"]


def test_adaptive_selection_prefers_personal_evidence_without_fixed_source_quota():
    personal = _doc(
        "personal-plan",
        "我的培养方案",
        "大一课程包括高等数学、程序设计和大学英语，学分与学期安排见教学进程表。",
        user=True,
        score=0.7,
    )
    public = _doc(
        "public-plan",
        "专业培养方案说明",
        "官网介绍专业培养目标和课程体系。",
        score=0.95,
    )
    bundle = EvidenceBundle(
        query="我的信计培养方案大一课程和学分",
        evidences=[public, personal],
        retrievers=["campus_rag", "user_docs"],
        subquestions=[SubQuestion(
            id="q1",
            query="我的信计培养方案大一课程和学分",
            retrievers=["campus_rag", "user_docs"],
        )],
        diagnostics={"knowledge_scope": "with_personal"},
    )

    selected, relevance, diagnostics = PersonalEvidencePolicy().select(bundle)

    assert relevance[0].level == "high"
    assert selected[0].retriever == "user_docs"
    assert diagnostics["selected_personal_count"] >= 1
    assert diagnostics["context_chars"] > 0
