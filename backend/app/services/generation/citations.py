from pydantic import ValidationError

from app.core.errors import DocumentError
from app.schemas.answer import EvidenceSource, GeneratedAnswer


def validate_answer(raw: str, sources: list[EvidenceSource]) -> GeneratedAnswer:
    try:
        if len(raw) > 32000:
            raise ValueError("Oversized output")
        answer = GeneratedAnswer.model_validate_json(raw)
    except (ValidationError, ValueError, TypeError):
        raise DocumentError(
            "invalid_model_output", "The model returned an invalid answer format.", 502
        ) from None
    allowed = {source.source_id for source in sources}
    if any(identifier not in allowed for identifier in answer.citations):
        raise DocumentError(
            "invalid_citations", "The model cited an unavailable source. Please retry.", 502
        )
    if answer.status == "answered" and not answer.citations:
        raise DocumentError(
            "invalid_citations", "The model returned an answer without citations.", 502
        )
    if answer.status == "insufficient_evidence" and answer.citations:
        raise DocumentError(
            "invalid_model_output", "The model returned contradictory evidence status.", 502
        )
    answer.citations = list(dict.fromkeys(answer.citations))
    if answer.status == "insufficient_evidence":
        # Do not display a substantive model answer disguised as an abstention.
        answer.answer = (
            "The retrieved passages do not provide enough evidence to answer this question."
        )
    return answer
