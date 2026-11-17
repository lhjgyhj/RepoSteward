# 安装入库测试：installation created 写入 Installation 与仓库；同一 delivery 不重复插 Event
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
from app.models import Event, Installation, Repository

# 夹具 id 取明显不可能是真实 GitHub 数据的值，避免撞库
INSTALLATION_ID = 910000001
REPO_ID = 910000002
REPO_NAME = "hello-world"
DELIVERY_CREATED = "t4-delivery-created"
DELIVERY_DUP_INSTALL = "t4-delivery-dup-install"
DELIVERY_DUP = "t4-delivery-dup"


@pytest.fixture
def anyio_backend() -> str:
    """只跑 asyncio 后端，环境里没有 trio。"""
    return "asyncio"


async def _clean_fixtures() -> None:
    """按外键顺序清掉这批夹具数据：Event → Repository → Installation。"""
    async with SessionLocal() as session:
        repo_ids = (
            await session.execute(select(Repository.id).where(Repository.github_repo_id == REPO_ID))
        ).scalars().all()
        if repo_ids:
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


def _installation_payload(action: str = "created") -> dict:
    return {
        "action": action,
        "installation": {
            "id": INSTALLATION_ID,
            "account": {"login": "octocat"},
        },
        "repositories": [
            {"id": REPO_ID, "name": REPO_NAME, "full_name": "octocat/hello-world"},
        ],
    }


@pytest.mark.anyio
async def test_installation_created_records_installation_and_repos() -> None:
    """合法签名的 installation created 之后，库里有 Installation 和仓库。"""
    await _clean_fixtures()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            status_code = await _post(ac, "installation", DELIVERY_CREATED, _installation_payload())
        assert status_code == 202

        async with SessionLocal() as session:
            installation = (
                await session.execute(
                    select(Installation).where(
                        Installation.github_installation_id == INSTALLATION_ID
                    )
                )
            ).scalar_one_or_none()
            repository = (
                await session.execute(
                    select(Repository).where(Repository.github_repo_id == REPO_ID)
                )
            ).scalar_one_or_none()

        assert installation is not None
        assert installation.account == "octocat"
        assert installation.plan == "free"

        assert repository is not None
        assert repository.name == REPO_NAME
        assert repository.installation_id == installation.id
    finally:
        await _clean_fixtures()
        # 每个测试用自己的事件循环，关掉本循环里建立的连接，避免下条测试复用死连接
        await engine.dispose()


@pytest.mark.anyio
async def test_duplicate_delivery_does_not_insert_second_event() -> None:
    """同一 X-GitHub-Delivery 两次 POST，Event 仍一行且都返回 202。"""
    await _clean_fixtures()
    try:
        # installation 事件不带单数 repository 键，只用来把仓库行准备好
        issues_payload = {
            "action": "opened",
            "repository": {"id": REPO_ID, "name": REPO_NAME},
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            install_status = await _post(
                ac, "installation", DELIVERY_DUP_INSTALL, _installation_payload()
            )
            first_status = await _post(ac, "issues", DELIVERY_DUP, issues_payload)
            second_status = await _post(ac, "issues", DELIVERY_DUP, issues_payload)

        assert install_status == 202
        assert first_status == 202
        assert second_status == 202

        async with SessionLocal() as session:
            event_count = (
                await session.execute(
                    select(func.count())
                    .select_from(Event)
                    .where(Event.delivery_id == DELIVERY_DUP)
                )
            ).scalar_one()
            event = (
                await session.execute(select(Event).where(Event.delivery_id == DELIVERY_DUP))
            ).scalar_one_or_none()
            repository = (
                await session.execute(
                    select(Repository).where(Repository.github_repo_id == REPO_ID)
                )
            ).scalar_one_or_none()

        assert event_count == 1
        assert event is not None
        assert event.type == "issues"
        assert repository is not None
        assert event.repo_id == repository.id
    finally:
        await _clean_fixtures()
        await engine.dispose()
