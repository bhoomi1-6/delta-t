"""Step-by-step logging for the planning workflow."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger("delta_t")


@contextmanager
def step(name: str) -> Iterator[None]:
    """Log when a workflow step starts and how long it took (or that it failed)."""
    logger.info("[%s] start", name)
    started = time.perf_counter()
    try:
        yield
    except Exception:
        logger.exception("[%s] FAILED after %.1fs", name, time.perf_counter() - started)
        raise
    logger.info("[%s] done in %.1fs", name, time.perf_counter() - started)
