"""台本をチャンク分割し、Gemini TTS（マルチスピーカー）で音声化するモジュール。"""

import base64
import logging

from google import genai
from google.genai import types

import config
from retry_utils import call_with_fallback

logger = logging.getLogger(__name__)


def chunk_turns(turns: list[dict], max_chars: int = config.TTS_MAX_CHUNK_CHARS) -> list[list[dict]]:
    """発話単位ではなく、台本全体をmax_chars未満のまとまり(チャンク)に区切る。
    1チャンク = 1回のTTS APIコールに対応させる。"""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_len = 0

    for turn in turns:
        line_len = len(turn["speaker"]) + 2 + len(turn["text"]) + 1
        if current and current_len + line_len > max_chars:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(turn)
        current_len += line_len

    if current:
        chunks.append(current)

    logger.info("台本を %d 個のTTSチャンクに分割しました。", len(chunks))
    return chunks


def _build_transcript(chunk: list[dict]) -> str:
    lines = [f"{turn['speaker']}: {turn['text']}" for turn in chunk]
    return "次の対話を、自然な日本語の会話として読み上げてください。\n" + "\n".join(lines)


def _speech_config() -> types.SpeechConfig:
    return types.SpeechConfig(
        multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
            speaker_voice_configs=[
                types.SpeakerVoiceConfig(
                    speaker=name,
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=info["voice"])
                    ),
                )
                for name, info in config.SPEAKERS.items()
            ]
        )
    )


def _extract_pcm_bytes(response) -> bytes:
    part = response.candidates[0].content.parts[0]
    data = part.inline_data.data
    if isinstance(data, str):
        data = base64.b64decode(data)
    if not data:
        raise ValueError("Geminiからの音声データが空でした。")
    return data


def synthesize_chunk(client: genai.Client, chunk: list[dict], chunk_index: int) -> bytes:
    transcript = _build_transcript(chunk)

    def build_fn(model: str):
        def _call():
            response = client.models.generate_content(
                model=model,
                contents=transcript,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=_speech_config(),
                ),
            )
            return _extract_pcm_bytes(response)

        return _call

    logger.info("チャンク %d の音声を生成します（%d文字）。", chunk_index, len(transcript))
    return call_with_fallback(
        f"tts_chunk_{chunk_index}",
        build_fn(config.TTS_MODEL),
        build_fn(config.TTS_FALLBACK_MODEL),
        config.RETRY_ATTEMPTS,
        config.RETRY_WAIT_SECONDS,
    )
