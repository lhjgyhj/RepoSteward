# 决策层 D2 测试：rules 后端按关键词判 issue 类型，未命中回「不确定」（报告 §6.1）
from app.services.decide import decide


def test_d2_bug_like_text_returns_bug() -> None:
    """标题带 crash、正文带 traceback → bug。"""
    state = {
        "title": "Crash on startup",
        "body": "Traceback (most recent call last):\n  File ...",
    }
    assert decide(state, ["D2"])["D2"] == "bug"


def test_d2_unmatched_returns_uncertain() -> None:
    """普通闲聊，没有任何关键词 → 不确定。"""
    state = {"title": "问候", "body": "今天天气不错，随便聊聊"}
    assert decide(state, ["D2"])["D2"] == "不确定"


def test_questions_without_d2_does_not_invent_d2() -> None:
    """没问 D2 时返回的字典里不能出现 D2 键。"""
    state = {"title": "Crash on startup"}

    assert decide(state, []) == {}
    assert "D2" not in decide(state, ["D1"])


def test_d2_feature_request_text_returns_feature() -> None:
    """带功能请求关键词 → 功能请求。"""
    state = {"title": "希望增加导出功能", "body": "能否支持按时间筛选"}
    assert decide(state, ["D2"])["D2"] == "功能请求"


def test_d2_missing_fields_returns_uncertain() -> None:
    """state 缺 title/body 也不能抛异常，回不确定。"""
    assert decide({}, ["D2"])["D2"] == "不确定"


def test_d2_non_rules_backend_returns_uncertain() -> None:
    """非 rules 后端本阶段不接模型，问 D2 一律回不确定。"""
    state = {"title": "Crash on startup"}
    assert decide(state, ["D2"], backend="deepseek_json")["D2"] == "不确定"
