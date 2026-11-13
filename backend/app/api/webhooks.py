# Webhook 接收端点：POST /webhooks/github，验签、入库去重、快速过滤后返回 202（报告 §4.2 第 1~3 步、F2.1~F2.3）

from fastapi import APIRouter, Header, Request, Response

from app.security import verify_github_signature

router = APIRouter()


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> Response:
    """接收 GitHub Webhook：验签通过后入库并尽快返回 202。

    签名无效必须拒绝，不能返回 202。
    同一 X-GitHub-Delivery 重复到达时仍返回 202，且不得插入第二行。
    本阶段若仓库行尚不存在（T4 才写入），不要伪造仓库；先把验签与响应走通。
    """
    # TODO(核心): payload = 等待 request 的原始字节方法（方法名是 body）
    payload = await request.body()
    # TODO(核心): 若 verify_github_signature(payload, x_hub_signature_256) 为假：
    #     return Response(status_code=401)
    if verify_github_signature(payload, x_hub_signature_256) is False:
        return Response(status_code=401)
    if not x_github_delivery or not x_github_event:
        return Response(status_code=400)

    # 写入 Event 依赖仓库行，与 T4 一起做。本阶段验签通过即 202。
    # TODO(核心): 验签已通过且头齐全后：return Response(status_code=202)
    return Response(status_code=202)
