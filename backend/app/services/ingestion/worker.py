import json
import sys

from app.core.errors import DocumentError
from app.services.ingestion.pdf import extract_pages


def main() -> None:
    try:
        pages = extract_pages(sys.stdin.buffer.read(), *map(int, sys.argv[1:]))
        payload = {"pages": pages}
    except DocumentError as exc:
        payload = {"error": exc.code, "message": exc.message}
    sys.stdout.buffer.write(json.dumps(payload).encode("utf-8"))


if __name__ == "__main__":
    main()
