# issue 分流服务：新开 issue 落库后调用 decide 判 D2，写入 Decision 与待审 Suggestion（报告 §6.1、F5.1）

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Decision, Event, Suggestion
from app.services.decide import decide


async def record_issue_triage(session: AsyncSession, event: Event, payload: dict) -> None:
    """为刚落库的 issues/opened 事件写 D2 决策与 pending 建议。

    Event 必须已 session.add 但尚未 commit：本函数先 flush 取主键，Decision 与
    Suggestion 才有 event_id 可挂。答案即使是「不确定」也照样写两行。
    没有 D2 答案时跳过写库。不提交事务，由 webhook 端点统一 commit。
    """
    # add 之后 event.id 通常还是 None，flush 才有主键
    await session.flush()

    issue = payload.get("issue") or {}
    # 只取 title/body，不把整份 payload 当 state
    state = {
        "title": issue.get("title") or "",
        "body": issue.get("body") or "",
    }
    answers = decide(state, ["D2"], backend="rules")
    answer = answers.get("D2")
    if answer is None:
        return

    session.add(Decision(
        event_id=event.id,
        point="D2",
        backend="rules",
        answer=answer,
    ))
    session.add(Suggestion(
        event_id=event.id,
        action="label",
        payload={"type": answer},
        mode="suggest",
        status="pending",
        decided_by=None,
    ))
