"""Waiting on the requests of a job run in parallel (``KNOWHOW_VLM_CONCURRENCY``, spec 04 AC-30).

The sequential loop stops at the first error: so does :func:`wait_first_error`. The requests not
started yet are cancelled; the ones already running (at most the pool size) finish on their own.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import FIRST_EXCEPTION, CancelledError, Future, wait
from typing import Any

#: Seconds between checks. ``concurrent.futures.wait`` is not woken when a queued future is cancelled
#: (``Executor.shutdown(cancel_futures=True)`` after another run failed): it would wait forever.
POLL_S = 0.2


def wait_first_error(futures: Sequence[Future[Any]]) -> None:
    """Return once every future is done; at the first error cancel the rest and raise it.

    ``KeyboardInterrupt`` while waiting cancels the rest too. A future cancelled from outside (the
    pool was shut down because another run failed) ends the wait with ``CancelledError``.
    """
    try:
        while not all(future.done() for future in futures) and not any(map(_failed, futures)):
            wait(futures, timeout=POLL_S, return_when=FIRST_EXCEPTION)
    except BaseException:
        cancel(futures)
        raise
    for future in futures:
        if _failed(future):
            cancel(futures)
            error = future.exception()
            assert error is not None
            raise error
    if any(future.cancelled() for future in futures):
        raise CancelledError


def _failed(future: Future[Any]) -> bool:
    return future.done() and not future.cancelled() and future.exception() is not None


def cancel(futures: Sequence[Future[Any]]) -> None:
    for future in futures:
        future.cancel()
