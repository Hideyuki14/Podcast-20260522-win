"""調査結果(research.json相当)から男女二人の対話台本(script.json相当)を生成するモジュール。"""

import json
import logging

from google import genai
from google.genai import types

import config
from retry_utils import call_with_fallback

logger = logging.getLogger(__name__)

SPEAKER_NAMES = list(config.SPEAKERS.keys())


def _build_prompt(research: dict) -> str:
    speaker_a, speaker_b = SPEAKER_NAMES
    return f"""あなたはPodcast番組の放送作家です。以下のリサーチメモをもとに、
{speaker_a}（男性）と{speaker_b}（女性）の二人が自然な日本語で語り合うPodcast台本を作成してください。

## リサーチメモ
バージョン: {research.get('version')}
{research.get('summary')}

## 台本の条件
- 話者は必ず「{speaker_a}」「{speaker_b}」の二人のみとし、掛け合い形式にすること
- 明るく親しみやすいが、内容は技術的に深く踏み込んだ「Claude Code {research.get('version')}」の解説Podcastにすること
- 冒頭で挨拶と今回のバージョンの紹介、最後は簡単なまとめで締めること
- 全体の発話文字数の合計はおよそ{config.SCRIPT_TARGET_CHAR_MIN}〜{config.SCRIPT_TARGET_CHAR_MAX}文字程度（読み上げて5分程度になる分量）
- 出力は必ず次のJSON形式のみとし、それ以外の文章（説明やコードフェンス）は一切含めないこと

## 出力JSON形式
{{
  "turns": [
    {{"speaker": "{speaker_a}", "text": "発話内容"}},
    {{"speaker": "{speaker_b}", "text": "発話内容"}}
  ]
}}
"""


def _parse_script_json(text: str) -> list[dict]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"台本のJSON解析に失敗しました: {exc}") from exc

    turns = data.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError("台本JSONに有効な turns 配列がありません。")
    for turn in turns:
        if turn.get("speaker") not in config.SPEAKERS:
            raise ValueError(f"未知の話者名です: {turn.get('speaker')}")
        if not turn.get("text"):
            raise ValueError("空の発話が含まれています。")
    return turns


def write_script(client: genai.Client, research: dict) -> dict:
    prompt = _build_prompt(research)

    def build_fn(model: str):
        def _call():
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            if not response.text:
                raise ValueError("Geminiからの台本生成結果が空でした。")
            turns = _parse_script_json(response.text)
            return turns

        return _call

    turns = call_with_fallback(
        "script_writer",
        build_fn(config.RESEARCH_MODEL),
        build_fn(config.RESEARCH_FALLBACK_MODEL),
        config.RETRY_ATTEMPTS,
        config.RETRY_WAIT_SECONDS,
    )

    total_characters = sum(len(t["text"]) for t in turns)
    logger.info("台本を生成しました（発話数: %d, 合計文字数: %d）。", len(turns), total_characters)

    return {
        "version": research.get("version"),
        "turns": turns,
        "total_characters": total_characters,
    }
