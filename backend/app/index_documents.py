"""Run from backend/: uv run python -m app.index_documents --all (or --document UUID)."""

import argparse
import json
from uuid import UUID

from sqlalchemy import select

from app.core.config import Settings
from app.db.session import make_session_factory
from app.models.document import Document
from app.services.embeddings.encoder import LocalEncoder
from app.services.embeddings.indexing import IndexingService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--document", type=UUID)
    args = parser.parse_args()
    settings = Settings()
    if settings.database_url is None:
        parser.error("Set TRACERAG_DATABASE_URL first")
    engine, sessions = make_session_factory(settings.database_url.get_secret_value())
    try:
        service = IndexingService(sessions, LocalEncoder(settings))
        with sessions() as session:
            identifiers = (
                list(session.scalars(select(Document.id).where(Document.status == "ready")))
                if args.all
                else [args.document]
            )
        for identifier in identifiers:
            print(json.dumps(service.index(identifier).model_dump(mode="json")))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
