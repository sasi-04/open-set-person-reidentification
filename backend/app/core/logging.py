"""
Logging with request IDs.

In plain words: every HTTP request gets a short random ID. The ID is printed
on every log line written while that request is being handled, and is also
returned to the client in the ``X-Request-ID`` header, so a problem report
("request 3f9a1c...") can be traced end to end.

Privacy rule enforced by convention: we log *what happened* (route, status,
timings, counts). We never log image bytes, embeddings or file contents.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

# "-" is shown for log lines written outside a request (startup, background jobs).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")
    )
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn's own access log would duplicate our request log line.
    logging.getLogger("uvicorn.access").disabled = True
