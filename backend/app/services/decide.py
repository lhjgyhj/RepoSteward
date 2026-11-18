# 决策层统一接口 decide(state, questions)->answers，本阶段 rules 后端打通 D2（报告 §6.1）
# rules 只能返回确定性答案，答案集与报告 §6.1 一致；无法判定时返回「不确定」，交给后续模型再审

# D2 issue 类型的合法答案，顺序即报告里的选项顺序
D2_OPTIONS = ("bug", "功能请求", "使用提问", "文档", "垃圾", "不确定")

# 关键词表按优先级排列：先命中先返回，命中即停
_SPAM_KEYWORDS = ("spam", "广告", "加微信", "刷单")
_DOC_KEYWORDS = ("readme", "文档", "typo", "错别字")
# 故意不收单独的 "error"：普通报错描述里太常见，会把使用提问误判成 bug
_BUG_KEYWORDS = ("traceback", "crash", "exception", "报错", "崩溃")
_FEATURE_KEYWORDS = ("希望增加", "feature", "能否支持", "希望有")
_QUESTION_KEYWORDS = ("怎么用", "如何", "怎么")


def decide(state: dict, questions: list[str], backend: str = "rules") -> dict[str, str]:
    """按 questions 逐个回答决策点，只返回被问到的键。

    本阶段只实现 D2（issue 类型）。backend 为 "rules" 时按关键词判定；
    其它 backend 尚未接入，问 D2 时一律回「不确定」，不发起任何网络请求。
    """
    answers: dict[str, str] = {}
    if "D2" in questions:
        answers["D2"] = _decide_d2(state) if backend == "rules" else "不确定"
    return answers


def _decide_d2(state: dict) -> str:
    """把 title 与 body 拼成小写文本，按关键词优先级判 issue 类型。"""
    text = ((state.get("title") or "") + "\n" + (state.get("body") or "")).lower()

    for keywords, answer in (
        (_SPAM_KEYWORDS, "垃圾"),
        (_DOC_KEYWORDS, "文档"),
        (_BUG_KEYWORDS, "bug"),
        (_FEATURE_KEYWORDS, "功能请求"),
        (_QUESTION_KEYWORDS, "使用提问"),
    ):
        if _contains_any(text, keywords):
            return answer

    return "不确定"


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)
