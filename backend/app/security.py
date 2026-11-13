# Webhook 验签：校验 X-Hub-Signature-256，签名不符的事件直接丢弃（报告 §4.2 第 1 步、F2.2）
import hashlib
import hmac

from app.config import settings


def verify_github_signature(payload: bytes, signature_header: str | None) -> bool:
    """判断 GitHub Webhook 请求的签名是否有效。

    参数:
        payload: 请求体的原始字节，必须用原文，不要先解码再重新编码。
        signature_header: 请求头 X-Hub-Signature-256 的值，可能缺失。

    返回:
        True 表示有效；False 表示无效。
        密钥为空、签名头缺失、格式不对、比对失败，都算无效。
    """
    secret = settings.GITHUB_WEBHOOK_SECRET

    if not secret or not signature_header:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    received = signature_header.removeprefix(prefix)

    # TODO(核心): 把 secret 转成字节，对 payload 做 HMAC-SHA256，得到十六进制字符串 expected
    # 标准库：hmac、hashlib.sha256。密钥和正文都必须是 bytes。
    secret_bytes = secret.encode("utf-8")
    expected = hmac.new(
        key = secret_bytes,
        msg = payload,
        digestmod = hashlib.sha256
    ).hexdigest()
    # TODO(核心): 用 hmac.compare_digest(expected, received) 做耗时固定比较并返回
    # 不要用 == 。expected 还没算出来时不要提前 return True。
    return hmac.compare_digest(expected, received)
