# 控制台登录：GitHub OAuth 授权码流程，会话里只保留当前用户与其有维护权限的仓库（报告 §5.1 F1.2）
# 会话由 Starlette SessionMiddleware 以签名 cookie 承载，键 github_user 存
# {"login": ..., "github_id": ..., "repo_ids": [...]}。

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.config import settings

router = APIRouter()

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_REPOS_URL = "https://api.github.com/user/repos"
GITHUB_TIMEOUT_SECONDS = 10.0

# 本地开发与测试没配 SESSION_SECRET 时用的固定占位，生产必须通过环境变量覆盖
DEV_SESSION_SECRET = "dev-insecure-session"

# GitHub 仓库 permissions 里任一为真即视为可维护
MAINTAIN_PERMISSIONS = ("admin", "maintain", "push")


class GitHubAuthError(Exception):
    """调用 GitHub 失败：携带建议回给前端的 HTTP 状态码，避免冒成 500。"""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def session_secret() -> str:
    """会话签名密钥，未配置时退回固定开发占位。"""
    return settings.SESSION_SECRET or DEV_SESSION_SECRET


def _callback_url(request: Request) -> str:
    """拼出回调地址的绝对 URL，host 跟实际请求走，不写死端口。"""
    return str(request.base_url).rstrip("/") + "/api/auth/callback"


def _authorized_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    }


def _can_maintain(permissions: dict) -> bool:
    return any(permissions.get(key) for key in MAINTAIN_PERMISSIONS)


def _json_object(response: httpx.Response) -> dict:
    """解析 GitHub 的 JSON 响应，只当对象处理；非 JSON 或数组视为空，避免 500。"""
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _json_list(response: httpx.Response) -> list:
    """解析 GitHub 的 JSON 响应，只当列表处理；非 JSON 或对象返回空列表。"""
    try:
        data = response.json()
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def _maintainable_repo_ids(repos: object) -> list[int]:
    """从 GitHub 仓库列表里挑出有维护权限的仓库 id，去重并排序。"""
    if not isinstance(repos, list):
        return []
    repo_ids = {
        repo["id"]
        for repo in repos
        if isinstance(repo, dict) and "id" in repo and _can_maintain(repo.get("permissions") or {})
    }
    return sorted(repo_ids)


async def fetch_github_identity(code: str) -> dict:
    """用授权码换 access_token，再取 GitHub 用户与仓库，返回会话里的 github_user 结构。

    仓库纳入条件：permissions 里 admin、maintain、push 任一为真。
    """
    async with httpx.AsyncClient(timeout=GITHUB_TIMEOUT_SECONDS) as client:
        try:
            token_response = await client.post(
                GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                },
            )
            token_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GitHubAuthError("连接 GitHub 换取访问令牌失败") from exc

        token = _json_object(token_response).get("access_token")
        if not token:
            # GitHub 对无效/过期授权码返回 200 + error 字段，按未授权处理
            raise GitHubAuthError("GitHub 未返回访问令牌，授权码可能已失效", status_code=401)

        headers = _authorized_headers(token)
        try:
            user_response = await client.get(GITHUB_USER_URL, headers=headers)
            user_response.raise_for_status()
            repos_response = await client.get(
                GITHUB_REPOS_URL,
                headers=headers,
                params={
                    "per_page": 100,
                    "affiliation": "owner,collaborator,organization_member",
                },
            )
            repos_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GitHubAuthError("读取 GitHub 用户或仓库信息失败") from exc

    user = _json_object(user_response)
    repos = _json_list(repos_response)

    return {
        "login": user.get("login", ""),
        "github_id": user.get("id"),
        "repo_ids": _maintainable_repo_ids(repos),
    }


@router.get("/api/auth/login")
async def login(request: Request) -> RedirectResponse:
    """生成随机 state 写进会话，跳转 GitHub 授权页。"""
    if not settings.GITHUB_CLIENT_ID:
        raise HTTPException(status_code=500, detail="未配置 GITHUB_CLIENT_ID，无法发起 GitHub 登录")

    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    query = urlencode({
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": _callback_url(request),
        "scope": "read:user repo",
        "state": state,
    })
    return RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{query}", status_code=302)


@router.get("/api/auth/callback")
async def github_callback(
    request: Request,
    code: str = "",
    state: str = "",
) -> RedirectResponse:
    """校验 state 与授权码，把身份写进会话后跳回前端。"""
    expected_state = request.session.get("oauth_state")
    state_ok = bool(expected_state) and bool(state) and secrets.compare_digest(
        str(expected_state).encode("utf-8"), state.encode("utf-8")
    )
    if not state_ok:
        raise HTTPException(status_code=400, detail="state 校验失败，请重新发起登录")

    if not code:
        raise HTTPException(status_code=400, detail="缺少 GitHub 授权码 code")

    request.session.pop("oauth_state", None)
    try:
        identity = await fetch_github_identity(code)
    except GitHubAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    request.session["github_user"] = identity
    return RedirectResponse(settings.FRONTEND_URL, status_code=302)


@router.get("/api/auth/me")
async def me(request: Request) -> dict:
    """返回当前登录用户；未登录返回 401。"""
    github_user = request.session.get("github_user")
    if not github_user:
        raise HTTPException(status_code=401, detail="未登录")

    return {
        "login": github_user.get("login"),
        "github_id": github_user.get("github_id"),
        "repo_ids": github_user.get("repo_ids") or [],
    }


@router.post("/api/auth/logout")
async def logout(request: Request) -> Response:
    """清空会话，未登录调用也返回 204。"""
    request.session.clear()
    return Response(status_code=204)
