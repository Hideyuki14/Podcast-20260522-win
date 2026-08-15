"""PCM -> WAV -> MP3 変換モジュール（FFmpeg利用、pydub経由）。"""

import logging
import wave
from pathlib import Path

from pydub import AudioSegment

import config

logger = logging.getLogger(__name__)


def pcm_to_wav(pcm_bytes: bytes, wav_path: Path) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(config.TTS_CHANNELS)
        wf.setsampwidth(config.TTS_SAMPLE_WIDTH)
        wf.setframerate(config.TTS_SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    logger.info("WAVチャンクを保存しました: %s", wav_path)


def concatenate_to_mp3(wav_paths: list[Path], mp3_path: Path) -> None:
    combined = AudioSegment.empty()
    for wav_path in wav_paths:
        combined += AudioSegment.from_wav(str(wav_path))
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(mp3_path), format="mp3")
    logger.info(
        "MP3を書き出しました: %s（再生時間: 約%.1f分）",
        mp3_path,
        len(combined) / 1000 / 60,
    )
