"""Podcast自動生成パイプラインのエントリポイント。

処理順序: 調査(research) -> 台本(script) -> 音声合成(tts) -> 結合(mp3) -> Driveアップロード -> 状態更新

各段階の成果物は生成され次第 output/ に書き出すため、途中で失敗しても
それまでの成果物はディスク上に残る（失敗時のコミットはGitHub Actions側で実施）。
"""

import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google import genai

import audio
import config
import drive_upload
import research
import script_writer
import state
import tts
import video
from retry_utils import PipelineError

JST = ZoneInfo("Asia/Tokyo")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def resolve_target_date() -> date:
    override = os.environ.get(config.ENV_DATE_OVERRIDE, "").strip()
    if override:
        try:
            return date.fromisoformat(override)
        except ValueError:
            logger.warning("DATE_OVERRIDE の形式が不正なため無視します: %s", override)
    return datetime.now(JST).date()


def prepare_output_dir() -> None:
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # 前回実行の音声チャンクが残っていると結合時に混入するため、実行のたびにクリアする
    for path in config.OUTPUT_DIR.glob(f"{config.CHUNK_WAV_PREFIX}*.wav"):
        path.unlink()


def write_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    logger.info("JSONを保存しました: %s", path)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise PipelineError(f"環境変数 {name} が設定されていません。")
    return value


def run() -> None:
    target_date = resolve_target_date()
    logger.info("=== Podcast生成パイプライン開始（対象日: %s） ===", target_date.isoformat())

    prepare_output_dir()

    gemini_api_key = require_env(config.ENV_GEMINI_API_KEY)
    client = genai.Client(api_key=gemini_api_key)

    pipeline_state = state.load_state(config.STATE_FILE)

    logger.info("--- 1/4: 調査フェーズ ---")
    releases = research.get_github_releases()
    target_release, is_revisit = research.pick_target_release(
        releases, pipeline_state["researched_versions"]
    )
    if target_release is None:
        raise PipelineError("GitHub Releasesが取得できず、調査対象を決定できませんでした。")

    research_result = research.research_version(client, target_release, is_revisit)
    write_json(config.OUTPUT_DIR / config.RESEARCH_JSON_NAME, research_result)

    logger.info("--- 2/4: 台本生成フェーズ ---")
    script_result = script_writer.write_script(client, research_result)
    script_result["date"] = target_date.isoformat()
    write_json(config.OUTPUT_DIR / config.SCRIPT_JSON_NAME, script_result)

    logger.info("--- 3/4: 音声合成フェーズ ---")
    chunks = tts.chunk_turns(script_result["turns"])
    wav_paths: list[Path] = []
    for i, chunk in enumerate(chunks, start=1):
        pcm_bytes = tts.synthesize_chunk(client, chunk, i)
        wav_path = config.OUTPUT_DIR / f"{config.CHUNK_WAV_PREFIX}{i:02d}.wav"
        audio.pcm_to_wav(pcm_bytes, wav_path)
        wav_paths.append(wav_path)

    logger.info("--- 4/5: MP3結合フェーズ ---")
    mp3_path = config.OUTPUT_DIR / config.PODCAST_MP3_NAME
    audio.concatenate_to_mp3(wav_paths, mp3_path)

    logger.info("--- 5/5: MP4動画生成フェーズ（口パクアニメーション） ---")
    mp4_path = config.OUTPUT_DIR / config.PODCAST_MP4_NAME
    video.create_talking_avatar_video(
        chunks=chunks,
        wav_paths=wav_paths,
        mp3_path=mp3_path,
        mp4_path=mp4_path,
        version=target_release.get("tag_name"),
        date_str=target_date.isoformat(),
    )

    logger.info("--- Google Driveアップロード ---")
    dated_folder_name = f"{target_release.get('tag_name')}_{target_date.isoformat()}"
    drive_upload.upload_episode(
        client_id=require_env(config.ENV_GOOGLE_CLIENT_ID),
        client_secret=require_env(config.ENV_GOOGLE_CLIENT_SECRET),
        refresh_token=require_env(config.ENV_GOOGLE_REFRESH_TOKEN),
        dated_folder_name=dated_folder_name,
        files=[
            (mp3_path, "audio/mpeg"),
            (mp4_path, "video/mp4"),
            (config.OUTPUT_DIR / config.RESEARCH_JSON_NAME, "application/json"),
            (config.OUTPUT_DIR / config.SCRIPT_JSON_NAME, "application/json"),
        ],
    )

    # 全工程が成功した場合のみ調査済みとして記録する（途中失敗時は翌日以降に再挑戦させる）
    if not is_revisit:
        state.mark_covered(pipeline_state, target_release["tag_name"])
        state.save_state(config.STATE_FILE, pipeline_state)
    else:
        logger.info("再訪調査のため状態ファイルは更新しません。")

    logger.info("=== Podcast生成パイプラインが正常に完了しました ===")


def main() -> None:
    try:
        run()
    except Exception as exc:  # noqa: BLE001 - 失敗内容をログに残した上で異常終了させる
        logger.error("パイプラインが失敗しました: %s", exc, exc_info=True)
        logger.error("ここまでの途中成果物は output/ に保存されています。")
        sys.exit(1)


if __name__ == "__main__":
    main()
