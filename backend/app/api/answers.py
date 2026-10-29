from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.errors import DocumentError
from app.schemas.answer import AnswerResponse, AskRequest
from app.services.generation.answers import AnswerService

router = APIRouter(prefix="/api", tags=["answers"])


def get_answers(request: Request) -> AnswerService:
    if request.app.state.answers is None:
        raise DocumentError("database_unavailable", "Configure the document database first.", 503)
    return request.app.state.answers


@router.post("/ask", response_model=AnswerResponse)
async def ask(body: AskRequest, service: Annotated[AnswerService, Depends(get_answers)]):
    return await service.ask(body)
