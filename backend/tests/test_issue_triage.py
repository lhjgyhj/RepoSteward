# issue 分流测试：issues/opened 落库后写 D2 Decision 与 pending Suggestion；重复投递不重复写
# 请求与查库都跑在同一个事件循环里，避免 asyncpg 连接跨 loop 复用
import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import Decision, Event, Installation, Repository, Suggestion

# 夹具 id 与 T4（9100000xx）、T5（9100001xx）错开，避免撞库
INSTALLATION_ID = 910000301
REPO_ID = 910000302
REPO_NAME = "hello-world"
DELIVERY_INSTALL = "t3-delivery-install"
DELIVERY_CRASH = "t3-delivery-crash"
DELIVERY_DUP = "t3-delivery-dup"


@pytest.fixture
def anyio_backend() -> str:
    """只跑 asyncio 后端，环境里没有 trio。"""
    return "asyncio"


async def _clean_fixtures() -> None:
    """按外键顺序清掉这批夹具数据：Suggestion → Decision → Event → Repository → Installation。"""
    async with SessionLocal() as session:
        repo_ids = (
            await session.execute(select(Repository.id).where(Repository.github_repo_id == REPO_ID))
        ).scalars().all()
        if repo_ids:
            event_ids = (
                await session.execute(select(Event.id).where(Event.repo_id.in_(repo_ids)))
            ).scalars().all()
            if event_ids:
                await session.execute(
                    delete(Suggestion).where(Suggestion.event_id.in_(event_ids))
                )
                await session.execute(
                    delete(Decision).where(Decision.event_id.in_(event_ids))
                )
            await session.execute(delete(Event).where(Event.repo_id.in_(repo_ids)))
        await session.execute(delete(Repository).where(Repository.github_repo_id == REPO_ID))
        await session.execute(
            delete(Installation).where(Installation.github_installation_id == INSTALLATION_ID)
        )
        await session.commit()


def _sign(body: bytes) -> str:
    """按 GitHub 的算法给正文做 HMAC-SHA256 签名，返回 sha256=... 头。"""
    settings.GITHUB_WEBHOOK_SECRET = "test-secret"
    secret_bytes = settings.GITHUB_WEBHOOK_SECRET.encode("utf-8")
    digest = hmac.new(
        key=secret_bytes,
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return "sha256=" + digest


async def _post(ac: AsyncClient, event: str, delivery: str, payload: dict) -> int:
    """同一份字节既签名又发送，返回状态码。"""
    body = json.dumps(payload).encode("utf-8")
    response = await ac.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Delivery": delivery,
            "X-GitHub-Event": event,
        },
    )
    return response.status_code


def _installation_payload() -> dict:
    return {
        "action": "created",
        "installation": {
            "id": INSTALLATION_ID,
            "account": {"login": "octocat"},
        },
        "repositories": [
            {"id": REPO_ID, "name": REPO_NAME, "full_name": "octocat/hello-world"},
        ],
    }


def _crash_issue_payload() -> dict:
    """标题带 Crash、正文带 Traceback，rules 必然判成 bug。"""
    return {
        "action": "opened",
        "issue": {
            "title": "Crash on startup",
            "body": "Traceback (most recent call last):\n  File \"main.py\", line 1",
        },
        "repository": {"id": REPO_ID, "name": REPO_NAME},
    }


async def _triage_rows(
    delivery: str,
) -> tuple[Event | None, Decision | None, Suggestion | None]:
    """按 delivery_id 取这条事件的 Event、Decision、Suggestion（各取一行）。"""
    async with SessionLocal() as session:
        event = (
            await session.execute(select(Event).where(Event.delivery_id == delivery))
        ).scalar_one_or_none()
        if event is None:
            return None, None, None
        decision = (
            await session.execute(select(Decision).where(Decision.event_id == event.id))
        ).scalars().all()
        suggestion = (
            await session.execute(select(Suggestion).where(Suggestion.event_id == event.id))
        ).scalars().all()
    return (
        event,
        decision[0] if len(decision) == 1 else None,
        suggestion[0] if len(suggestion) == 1 else None,
    )


@pytest.mark.anyio
async def test_opened_issue_with_crash_writes_decision_and_pending_suggestion() -> None:
    """issues/opened 命中 bug 关键词后，写一行 D2 Decision 与一行 pending Suggestion。"""
    await _clean_fixtures()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            install_status = await _post(
                ac, "installation", DELIVERY_INSTALL, _installation_payload()
            )
            issue_status = await _post(ac, "issues", DELIVERY_CRASH, _crash_issue_payload())

        assert install_status == 202
        assert issue_status == 202

        event, decision, suggestion = await _triage_rows(DELIVERY_CRASH)

        assert event is not None
        assert event.type == "issues"

        assert decision is not None
        assert decision.event_id == event.id
        assert decision.point == "D2"
        assert decision.backend == "rules"
        assert decision.answer == "bug"

        assert suggestion is not None
        assert suggestion.event_id == event.id
        assert suggestion.action == "label"
        assert suggestion.mode == "suggest"
        assert suggestion.status == "pending"
        assert suggestion.decided_by is None
        assert suggestion.payload["type"] == "bug"
    finally:
        await _clean_fixtures()
        # 每个测试用自己的事件循环，关掉本循环里建立的连接，避免下条测试复用死连接
        await engine.dispose()


@pytest.mark.anyio
async def test_duplicate_delivery_does_not_duplicate_decision() -> None:
    """同一 X-GitHub-Delivery 的 issues 两次 POST：Event/Decision/Suggestion 各一行。"""
    await _clean_fixtures()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            install_status = await _post(
                ac, "installation", DELIVERY_INSTALL, _installation_payload()
            )
            first_status = await _post(ac, "issues", DELIVERY_DUP, _crash_issue_payload())
            second_status = await _post(ac, "issues", DELIVERY_DUP, _crash_issue_payload())

        assert install_status == 202
        assert first_status == 202
        assert second_status == 202

        async with SessionLocal() as session:
            event = (
                await session.execute(select(Event).where(Event.delivery_id == DELIVERY_DUP))
            ).scalar_one_or_none()
            decision_count = (
                await session.execute(
                    select(func.count()).select_from(Decision).where(Decision.event_id == event.id)
                )
            ).scalar_one()
            suggestion_count = (
                await session.execute(
                    select(func.count())
                    .select_from(Suggestion)
                    .where(Suggestion.event_id == event.id)
                )
            ).scalar_one()

        assert event is not None
        assert decision_count == 1
        assert suggestion_count == 1
    finally:
        await _clean_fixtures()
        await engine.dispose()


@pytest.mark.anyio
async def test_installation_event_does_not_write_decision() -> None:
    """installation 事件只建仓库，不给这批夹具写任何 Decision / Suggestion。"""
    await _clean_fixtures()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            status_code = await _post(ac, "installation", DELIVERY_INSTALL, _installation_payload())

        assert status_code == 202

        async with SessionLocal() as session:
            repo_ids = (
                await session.execute(
                    select(Repository.id).where(Repository.github_repo_id == REPO_ID)
                )
            ).scalars().all()
            decision_count = (
                await session.execute(
                    select(func.count())
                    .select_from(Decision)
                    .join(Event, Decision.event_id == Event.id)
                    .where(Event.repo_id.in_(repo_ids))
                )
            ).scalar_one()
            suggestion_count = (
                await session.execute(
                    select(func.count())
                    .select_from(Suggestion)
                    .join(Event, Suggestion.event_id == Event.id)
                    .where(Event.repo_id.in_(repo_ids))
                )
            ).scalar_one()

        assert repo_ids
        assert decision_count == 0
        assert suggestion_count == 0
    finally:
        await _clean_fixtures()
        await engine.dispose()
