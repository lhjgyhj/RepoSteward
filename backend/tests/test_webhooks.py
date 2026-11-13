# Webhook 端点测试：签名失败拒绝；合法请求返回 202（报告 F2.1~F2.3）
# 写入 Event 依赖仓库行，与 T4 一起联调，本文件先测验签与状态码。
import hashlib
import hmac

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)

def test_invalid_signature_is_not_accepted() -> None:
    """签名错误时不能返回 202。"""
    response = client.post(
        "/webhooks/github",
        content=b'{"action":"opened"}',
        headers={
            "X-Hub-Signature-256": "sha256=deadbeef",
            "X-GitHub-Delivery": "delivery-invalid",
            "X-GitHub-Event": "issues",
        },
    )
    assert response.status_code != 202


def test_valid_request_returns_202() -> None:
    """验签通过后返回 202。"""
    payload = b'{"action":"opened"}'
    settings.GITHUB_WEBHOOK_SECRET = "test-secret"
    secret_bytes = settings.GITHUB_WEBHOOK_SECRET.encode("utf-8")
    digest = hmac.new(
        key = secret_bytes,
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()
    signature_header = "sha256=" + digest
    response = client.post(
        "/webhooks/github",
        content=payload,
        headers={
            "X-Hub-Signature-256": signature_header,
            "X-GitHub-Delivery": "delivery-valid",
            "X-GitHub-Event": "issues",
        },
    )
    assert response.status_code == 202
