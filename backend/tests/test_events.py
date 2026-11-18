# 事件列表测试：未登录 401；登录后只返回自己有维护权限仓库的事件，新的在前。
# 第二条的请求与查库都跑在同一个事件循环里，避免 asyncpg 连接跨 loop 复用
import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from itsdangerous import TimestampSigner
from sqlalchemy import delete, select

from app.api.auth import session_secret
from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import Decision, Event, Installation, Repository, Suggestion

client = TestClient(app)

# 夹具 id 取明显不可能是真实 GitHub 数据的值，避免撞库
INSTALLATION_ID = 910000101
REPO_ID = 910000102
REPO_NAME = "hello-world"
DELIVERY_A = "t5-delivery-a"
DELIVERY_B = "t5-delivery-b"
DELIVERY_INSTALL = "t5-delivery-install"


def _session_cookie(session_data: dict) -> str:
    """按 SessionMiddleware 的算法（TimestampSigner + b64 json）造一个可用的会话 cookie。"""
    payload = base64.b64encode(json.dumps(session_data).encode("utf-8"))
    return TimestampSigner(session_secret()).sign(payload).decode("utf-8")


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
            # T3 起 issues/opened 会挂 Decision 与 Suggestion，必须先于 Event 删掉
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


def test_list_events_unauthorized_returns_401() -> None:
    """未登录 GET /api/events 返回 401，不泄露任何事件。"""
    response = client.get("/api/events")

    assert response.status_code == 401
    assert response.json() == {"detail": "未登录"}


def test_list_events_without_visible_repos_returns_empty_list() -> None:
    """已登录但会话里没有可见仓库时返回 200 与空列表，不查库、不 500。"""
    cookie = _session_cookie({"github_user": {"login": "octocat", "github_id": 1, "repo_ids": []}})

    with TestClient(app) as scoped_client:
        response = scoped_client.get("/api/events", headers={"Cookie": f"session={cookie}"})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_list_events_newest_first() -> None:
    """登录后库里两条事件时，GET /api/events 返回两条且新的在前。"""
    # 上一条用例的 TestClient 在自己的事件循环里建过连接，循环已关闭；
    # 先丢掉池里的死连接，再在本循环里重新建连
    await engine.dispose()
    await _clean_fixtures()
    try:
        # 当前登录用户只有 REPO_ID 这个仓库的维护权限，事件应能读到
        cookie = _session_cookie({
            "github_user": {"login": "octocat", "github_id": 1, "repo_ids": [REPO_ID]},
        })
        headers = {"Cookie": f"session={cookie}"}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            install_status = await _post(ac, "installation", DELIVERY_INSTALL, _installation_payload())
            # 再 POST 两条带 repository.id（910000102）的 issues 事件，用不同的 X-GitHub-Delivery
            issues_payload = {"action": "opened", "repository": {"id": REPO_ID, "name": REPO_NAME}}
            first_status = await _post(ac, "issues", DELIVERY_A, issues_payload)
            second_status = await _post(ac, "issues", DELIVERY_B, issues_payload)
            # 带登录 cookie 读列表，未登录会被 401 挡住
            response = await ac.get("/api/events", headers=headers)

        assert install_status == 202
        assert first_status == 202
        assert second_status == 202
        assert response.status_code == 200

        # 库里可能有别的事件，所以只查这两条在不在，不断言列表总长度
        items = response.json()
        delivery_ids = {item["delivery_id"] for item in items}
        assert DELIVERY_A in delivery_ids
        assert DELIVERY_B in delivery_ids

        # 我们刚插入的两条是最新的，降序后必然占住下标 0、1
        assert len(items) >= 2
        assert items[0]["received_at"] >= items[1]["received_at"]

        # 换一个只有别的仓库权限的会话，同样两条事件必须看不到（过滤真的生效）
        other_cookie = _session_cookie({
            "github_user": {"login": "other", "github_id": 2, "repo_ids": [REPO_ID + 1]},
        })
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            other_response = await ac.get(
                "/api/events", headers={"Cookie": f"session={other_cookie}"}
            )
        assert other_response.status_code == 200
        other_delivery_ids = {item["delivery_id"] for item in other_response.json()}
        assert DELIVERY_A not in other_delivery_ids
        assert DELIVERY_B not in other_delivery_ids
    finally:
        # 测完按外键顺序清理夹具：Event → Repository → Installation
        await _clean_fixtures()
        # 每个测试用自己的事件循环，关掉本循环里建立的连接，避免下条测试复用死连接
        await engine.dispose()
