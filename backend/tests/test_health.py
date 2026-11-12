# 探活接口测试：校验 GET /health 返回 200 与 {"status":"ok"}（报告 §9 第 1 周验收的前置自检）
# 本文件允许写完整实现，不写业务 import。

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
