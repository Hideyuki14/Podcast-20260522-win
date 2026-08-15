"""Gemini API 呼び出し向けの共通リトライ・フォールバック処理。"""

import logging
import time

from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)

# 429（レート制限）/ 500 / 503（サーバ側一時不可）はリトライ対象
RETRYABLE_HTTP_CODES = {429, 500, 503}


class PipelineError(Exception):
    """パイプライン内で回復不能と判断したエラー。"""


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.APIError):
        return getattr(exc, "code", None) in RETRYABLE_HTTP_CODES
    # モデル応答の形式不正（JSON解析失敗など）も一時的な揺らぎとみなし再試行する
    if isinstance(exc, ValueError):
        return True
    return False


def call_with_retry(label: str, fn, attempts: int, wait_seconds: int):
    """fn() を最大 attempts 回試行する。リトライ可能なエラーのみ待機して再試行する。"""
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - Gemini SDKの多様な例外を横断的に扱う
            last_exc = exc
            if _is_retryable(exc) and attempt < attempts:
                logger.warning(
                    "[%s] 試行 %d/%d が失敗しました（%s）。%d秒待機して再試行します。",
                    label, attempt, attempts, exc, wait_seconds,
                )
                time.sleep(wait_seconds)
                continue
            logger.error("[%s] 試行 %d/%d で最終的に失敗しました（%s）。", label, attempt, attempts, exc)
            raise
    raise last_exc  # pragma: no cover - 理論上到達しない


def call_with_fallback(label: str, primary_fn, fallback_fn, attempts: int, wait_seconds: int):
    """プライマリモデルで試行し、全て失敗したらフォールバックモデルでも同様に試行する。"""
    try:
        logger.info("[%s] プライマリモデルで実行します。", label)
        return call_with_retry(f"{label}:primary", primary_fn, attempts, wait_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[%s] プライマリモデルが %d回の試行後も失敗しました（%s）。フォールバックモデルに切り替えます。",
            label, attempts, exc,
        )
        return call_with_retry(f"{label}:fallback", fallback_fn, attempts, wait_seconds)
