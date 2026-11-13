# FastAPI 应用入口：创建应用实例、注册 /health 探活，并预留各路由挂载位置（报告 §4.1 三层分工）
# 本文件允许写完整实现，不写业务 import。

from fastapi import FastAPI

from app.api.webhooks import router as webhooks_router

app = FastAPI(title="RepoSteward 仓库管家", version="0.1.0")

app.include_router(webhooks_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """探活端点，供本地启动自检与后续部署健康检查使用。"""
    return {"status": "ok"}


# Webhook 路由已在文件头挂载：app.include_router(webhooks_router)，接收 GitHub 事件（§4.2 第 1~3 步）
# TODO(M1-T5) 挂载事件只读列表路由：app.include_router(events.router)，供控制台读取原始事件
# TODO(M1-T6) 挂载 GitHub OAuth 登录路由：app.include_router(auth.router)，控制台登录（F1.2）
