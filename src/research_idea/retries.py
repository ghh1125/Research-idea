"""One retry policy shared by research tasks and conversation turns."""
from __future__ import annotations

import time

from .backend_errors import ProviderError, RetryExhausted

RETRY_DELAY_S = 30
MAX_RETRIES = 10


def with_retries(invoke, *, progress, before_wait, on_failure):
    """Initial attempt plus ten retries. Budgets and checkpoints belong to caller.

    Only operational provider failures are retried. Evidence validation and
    local configuration errors retain their own existing handling.
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = invoke()
        except ProviderError as error:
            on_failure(error, attempt)
            if attempt == MAX_RETRIES:
                raise RetryExhausted(error, MAX_RETRIES) from None
            # Do not wait if the caller cannot afford another attempt.
            before_wait(RETRY_DELAY_S)
            progress(f'[retry] {error}\n{RETRY_DELAY_S} 秒后重试 · {attempt + 1}/{MAX_RETRIES} · Ctrl+C 停止')
            time.sleep(RETRY_DELAY_S)
        else:
            if attempt:
                progress(f'[recovered] 调用已恢复 · 第 {attempt} 次重试成功，继续当前步骤。')
            return result
