# 安装事件服务：处理 installation 事件，记录 Installation 与其下 Repository（报告 §5.1 F1.1）

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Installation, Repository


async def handle_installation(session: AsyncSession, payload: dict) -> None:
    """记录 installation 事件带来的安装及其仓库。

    同一 github_installation_id 重复到达时更新已有行，不重复插入；
    其下仓库按 github_repo_id 对齐，新增的插入、已有的更新。
    本函数不提交事务，由 webhook 端点统一 commit。
    """
    installation_data = payload.get("installation") or {}
    repositories = payload.get("repositories") or []

    github_installation_id = installation_data.get("id")
    if github_installation_id is None:
        return

    account = (installation_data.get("account") or {}).get("login") or ""
    plan = "free"

    result = await session.execute(
        select(Installation).where(
            Installation.github_installation_id == github_installation_id
        )
    )
    installation = result.scalar_one_or_none()
    if installation is None:
        installation = Installation(
            github_installation_id=github_installation_id,
            account=account,
            plan=plan,
        )
        session.add(installation)
        # 先 flush 取到主键，下面插仓库行时外键才有值
        await session.flush()
    else:
        installation.account = account
        installation.plan = plan

    for repo_data in repositories:
        repo_data = repo_data or {}
        github_repo_id = repo_data.get("id")
        if github_repo_id is None:
            continue
        name = repo_data.get("name") or repo_data.get("full_name") or ""

        repo_result = await session.execute(
            select(Repository).where(Repository.github_repo_id == github_repo_id)
        )
        repository = repo_result.scalar_one_or_none()
        if repository is None:
            session.add(Repository(
                installation_id=installation.id,
                github_repo_id=github_repo_id,
                name=name,
            ))
        else:
            repository.name = name
            repository.installation_id = installation.id
