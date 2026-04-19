from sqlalchemy.ext.asyncio import AsyncSession

from app.db.uow import UnitOfWork
from app.llm.client import llm_client
from app.services.guided_service import GuidedService
from app.services.task_service import TaskService


def make_task_service(session: AsyncSession) -> TaskService:
    return TaskService(uow=UnitOfWork(session), llm=llm_client)


def make_guided_service(session: AsyncSession) -> GuidedService:
    return GuidedService(uow=UnitOfWork(session), llm=llm_client)
