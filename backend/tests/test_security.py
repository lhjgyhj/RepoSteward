# Webhook 验签测试：正确签名应通过，错误或缺签名应拒绝（报告 F2.2）
import hashlib
import hmac

from app.config import settings
from app.security import verify_github_signature


def test_valid_signature_is_accepted() -> None:
    """正确密钥 + 匹配的签名头 → 返回 True。"""
    payload = b'{"action":"opened"}'
    settings.GITHUB_WEBHOOK_SECRET = "test-secret"
    # TODO(核心): 用与生产相同的算法构造 signature_header（形如 sha256=...）
    secret_bytes = settings.GITHUB_WEBHOOK_SECRET.encode("utf-8")
    digest  = hmac.new(
        key=secret_bytes,
        msg = payload,
        digestmod=hashlib.sha256
    ).hexdigest()
    signature_header = "sha256=" + digest
    # TODO(核心): assert verify_github_signature(payload, signature_header) is True
    assert verify_github_signature(payload, signature_header) is True

def test_wrong_secret_is_rejected() -> None:
    """密钥与签名不匹配 → 返回 False。"""
    payload = b'{"action":"opened"}'
    settings.GITHUB_WEBHOOK_SECRET = "test-secret"
    signature_header = "sha256=deadbeef"
    assert verify_github_signature(payload, signature_header) is False


def test_missing_header_is_rejected() -> None:
    """没有签名头 → 返回 False。"""
    settings.GITHUB_WEBHOOK_SECRET = "test-secret"
    assert verify_github_signature(b"{}", None) is False
