# 登录流程测试：授权跳转、未登录 401、回调写会话后 /api/auth/me 能读到用户。
# 全程不访问真实 GitHub，回调里的外部调用用 patch 换掉
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_module
from app.config import settings
from app.main import app

FAKE_IDENTITY = {"login": "octocat", "github_id": 1, "repo_ids": [910000102]}


async def _fake_fetch_github_identity(code: str) -> dict:
    """替代真实的 GitHub 调用，只回一个固定身份；签名与真实实现一致（async）。"""
    assert code == "fake-code"
    return dict(FAKE_IDENTITY)


@pytest.fixture
def client() -> TestClient:
    """每条用例一个新的客户端，cookie 罐不跨用例，登录态也就不会串。"""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _setup_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """登录跳转要求配置了 Client ID，测试里给一个明显假的值。"""
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_SECRET", "test-client-secret")


def _login_state(client: TestClient) -> str:
    """走一次 /api/auth/login，从 302 的 Location 里取出 state。"""
    login_response = client.get("/api/auth/login", follow_redirects=False)
    assert login_response.status_code == 302
    return parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]


def test_login_redirects_to_github_with_state(client: TestClient) -> None:
    """GET /api/auth/login 302 到 GitHub 授权页，带 client_id 与 state。"""
    response = client.get("/api/auth/login", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://github.com/login/oauth/authorize")

    query = parse_qs(urlparse(location).query)
    assert query["client_id"] == ["test-client-id"]
    assert query["state"][0]
    assert query["scope"] == ["read:user repo"]
    # 回调地址指向本应用，不写死前端端口
    assert query["redirect_uri"][0].endswith("/api/auth/callback")


def test_me_without_session_returns_401(client: TestClient) -> None:
    """未登录 GET /api/auth/me 返回 401，body 是中文提示。"""
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "未登录"}


def test_events_without_session_returns_401(client: TestClient) -> None:
    """未登录 GET /api/events 返回 401，看不到全库事件。"""
    response = client.get("/api/events")

    assert response.status_code == 401
    assert response.json() == {"detail": "未登录"}


def test_callback_sets_session_and_me_returns_user(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """state 校验通过后回调写会话，随后 /api/auth/me 返回该用户。"""
    monkeypatch.setattr(auth_module, "fetch_github_identity", _fake_fetch_github_identity)

    state = _login_state(client)
    # TestClient 自动带上 /login 返回的会话 cookie，state 才能对上
    callback_response = client.get(
        f"/api/auth/callback?code=fake-code&state={state}",
        follow_redirects=False,
    )
    assert callback_response.status_code == 302
    assert callback_response.headers["location"] == settings.FRONTEND_URL

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json() == FAKE_IDENTITY


def test_callback_with_wrong_state_returns_400(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """state 与会话里不一致时 400，不换取身份。"""
    monkeypatch.setattr(auth_module, "fetch_github_identity", _fake_fetch_github_identity)

    _login_state(client)
    response = client.get(
        "/api/auth/callback?code=fake-code&state=not-the-same-state",
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert client.get("/api/auth/me").status_code == 401


def test_maintainable_repo_ids_keeps_only_maintain_permissions() -> None:
    """仓库纳入条件是 admin / maintain / push 任一为真，只读仓库与坏数据都丢掉。"""
    repos = [
        {"id": 1, "permissions": {"admin": True, "push": True}},
        {"id": 2, "permissions": {"maintain": True, "push": False}},
        {"id": 3, "permissions": {"push": True, "pull": True}},
        {"id": 4, "permissions": {"admin": False, "maintain": False, "push": False}},
        {"id": 5},
        "not-a-repo",
    ]

    assert auth_module._maintainable_repo_ids(repos) == [1, 2, 3]
    # 空列表与非列表都不能直接抛异常，回调里 github 返回异常结构时不该 500
    assert auth_module._maintainable_repo_ids([]) == []
    assert auth_module._maintainable_repo_ids(None) == []


def test_logout_clears_session(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登录后 POST /api/auth/logout 返回 204，之后 /me 变回 401。"""
    monkeypatch.setattr(auth_module, "fetch_github_identity", _fake_fetch_github_identity)

    state = _login_state(client)
    client.get(f"/api/auth/callback?code=fake-code&state={state}", follow_redirects=False)
    assert client.get("/api/auth/me").status_code == 200

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_login_without_client_id_returns_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没配 GITHUB_CLIENT_ID 时登录入口直接 500，并说明缺哪个配置。"""
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "")

    response = client.get("/api/auth/login", follow_redirects=False)

    assert response.status_code == 500
    assert "GITHUB_CLIENT_ID" in response.json()["detail"]


@pytest.mark.parametrize("github_status", [401, 502])
def test_callback_github_failure_is_not_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    github_status: int,
) -> None:
    """调 GitHub 失败时按 GitHubAuthError 的状态码返回 401/502，不冒 500 堆栈。"""
    async def _failing_fetch(code: str) -> dict:
        raise auth_module.GitHubAuthError("GitHub 调用失败", status_code=github_status)

    monkeypatch.setattr(auth_module, "fetch_github_identity", _failing_fetch)

    state = _login_state(client)
    response = client.get(
        f"/api/auth/callback?code=fake-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == github_status
    assert client.get("/api/auth/me").status_code == 401
