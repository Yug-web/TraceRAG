import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.answers import router as answers_router
from app.api.documents import router as documents_router
from app.api.health import router
from app.api.search import router as search_router
from app.core.config import Settings
from app.core.errors import DocumentError
from app.db.session import make_session_factory
from app.services.embeddings.encoder import Encoder, LocalEncoder
from app.services.embeddings.indexing import IndexingService
from app.services.generation.answers import AnswerService
from app.services.generation.provider import AnswerProvider, GeminiProvider
from app.services.ingestion.documents import DocumentService
from app.services.retrieval.search import RetrievalService


def create_app(
    settings: Settings | None = None,
    encoder: Encoder | None = None,
    provider: AnswerProvider | None = None,
) -> FastAPI:
    settings = settings if settings is not None else Settings()
    engine = None
    service = None
    indexing = None
    retrieval = None
    answers = None
    if settings.database_url is not None:
        engine, sessions = make_session_factory(settings.database_url.get_secret_value())
        service = DocumentService(sessions, settings)
        encoder = encoder if encoder is not None else LocalEncoder(settings)
        indexing = IndexingService(sessions, encoder)
        retrieval = RetrievalService(sessions, encoder)
        answers = AnswerService(
            retrieval, provider if provider is not None else GeminiProvider(settings), settings
        )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield
        if engine is not None:
            engine.dispose()

    application = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.documents = service
    application.state.indexing = indexing
    application.state.retrieval = retrieval
    application.state.answers = answers
    application.include_router(router)
    application.include_router(documents_router)
    application.include_router(search_router)
    application.include_router(answers_router)

    @application.exception_handler(DocumentError)
    async def document_error(request: Request, exc: DocumentError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": {
                    "code": exc.code,
                    "message": exc.message,
                    "document_id": exc.document_id,
                }
            },
        )

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logging.getLogger(__name__).error("Database operation failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "code": "database_unavailable",
                    "message": "Document storage is unavailable.",
                    "document_id": None,
                }
            },
        )

    return application


app = create_app()
