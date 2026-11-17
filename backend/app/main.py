# FastAPI 应用入口：创建应用实例、挂会话中间件、注册各路由（报告 §4.1 三层分工）

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.auth import session_secret
from app.api.events import router as events_router
from app.api.webhooks import router as webhooks_router

app = FastAPI(title="RepoSteward 仓库管家", version="0.1.0")

# 会话中间件要在路由之前挂上，登录态（cookie 名 session）才对所有路由可见
app.add_middleware(SessionMiddleware, secret_key=session_secret())

app.include_router(webhooks_router)
app.include_router(events_router)
app.include_router(auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """探活端点，供本地启动自检与后续部署健康检查使用。"""
    return {"status": "ok"}


# Webhook 路由已挂载：接收 GitHub 事件（§4.2 第 1~3 步）
# 事件只读列表路由已挂载：按当前登录用户有维护权限的仓库过滤（F1.2）
# 登录路由已挂载：GitHub OAuth 授权码流程（F1.2）
