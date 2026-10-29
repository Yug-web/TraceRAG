import json

from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.schemas.answer import AnswerResponse, AskRequest, EvidenceSource, GeneratedAnswer
from app.schemas.search import SearchRequest
from app.services.generation.citations import validate_answer
from app.services.generation.provider import AnswerProvider
from app.services.retrieval.search import RetrievalService


class AnswerService:
    def __init__(self, retrieval: RetrievalService, provider: AnswerProvider, settings: Settings):
        self.retrieval = retrieval
        self.provider = provider
        self.settings = settings

    async def ask(self, request: AskRequest) -> AnswerResponse:
        retrieved = await run_in_threadpool(
            self.retrieval.search, SearchRequest(query=request.question, top_k=request.top_k)
        )
        remaining = self.settings.qa_context_chars
        sources = []
        for hit in retrieved.results:
            if remaining <= 0:
                break
            passage = hit.text[:remaining]
            if not passage.strip():
                continue
            sources.append(
                EvidenceSource(
                    **{
                        **hit.model_dump(),
                        "text": passage,
                        "end_char": hit.start_char + len(passage),
                        "source_id": f"S{len(sources) + 1}",
                    }
                )
            )
            remaining -= len(passage)
        if not sources:
            generated = GeneratedAnswer(
                status="insufficient_evidence",
                answer="There are no retrieved passages available to answer this question.",
                citations=[],
            )
        else:
            # JSON escaping prevents passages from accidentally closing a delimiter.
            prompt = json.dumps(
                {
                    "question": request.question,
                    "evidence": [
                        {"source_id": source.source_id, "text": source.text} for source in sources
                    ],
                },
                ensure_ascii=False,
            )
            generated = validate_answer(await self.provider.generate(prompt), sources)
        return AnswerResponse(
            **generated.model_dump(),
            sources=sources,
            model=self.settings.llm_model if sources else None,
            retrieval_profile_id=retrieved.profile_id,
            indexed_documents=retrieved.indexed_documents,
            unindexed_documents=retrieved.unindexed_documents,
        )
