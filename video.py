"""発話中のキャラクターが口パクするアニメーション動画(MP4)を生成するモジュール。

タイムスタンプの推定方法:
  Gemini TTSは複数の発話をまとめて1回のAPI呼び出しで音声化するため、
  「どの発話が音声の何秒目にあたるか」という正確な情報は得られない。
  そこで、TTSチャンクごとの実際の音声の長さを、そのチャンクに含まれる
  発話の文字数比で按分し、近似的なタイムライン（誰がいつ話しているか）を作る。

動画の作り方:
  1周期ぶんの静止画（フレーム）をPillowで1枚ずつ描画し、FFmpegで
  それらを画像シーケンスとして音声と結合してMP4にする（パラパラ漫画方式）。
"""

import logging
import subprocess
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont

import config

logger = logging.getLogger(__name__)

# Ubuntu の fonts-noto-cjk パッケージが提供する日本語対応フォント
FONT_CANDIDATES = [
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
]

BACKGROUND_COLOR = (17, 24, 39)
TEXT_COLOR = (245, 245, 245)
IDLE_RING_COLOR = (55, 65, 81)
ACTIVE_RING_COLOR = (250, 204, 21)
MOUTH_COLOR = (60, 20, 20)
AVATAR_DIAMETER = 260


def _find_font_path() -> Path | None:
    for path in FONT_CANDIDATES:
        if path.exists():
            return path
    logger.warning("日本語フォント(fonts-noto-cjk)が見つかりません。文字化けする可能性があります。")
    return None


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    font_path = _find_font_path()
    if font_path is None:
        return ImageFont.load_default()
    return ImageFont.truetype(str(font_path), size=size, index=0)


def _draw_centered_in_box(draw, text: str, font, box_x: float, box_width: float, y: float, fill) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    draw.text((box_x + (box_width - text_width) / 2, y), text, font=font, fill=fill)


def _get_wav_duration_seconds(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def build_turn_timeline(chunks: list[list[dict]], wav_paths: list[Path]) -> tuple[list[dict], float]:
    """各チャンクの実際の音声長を、含まれる発話の文字数比で按分して
    (speaker, start_sec, end_sec) のタイムラインを作る。戻り値は (タイムライン, 総時間)。"""
    timeline: list[dict] = []
    offset = 0.0
    for chunk_turns, wav_path in zip(chunks, wav_paths):
        duration = _get_wav_duration_seconds(wav_path)
        total_chars = sum(len(t["text"]) for t in chunk_turns) or 1
        cursor = offset
        for turn in chunk_turns:
            share = len(turn["text"]) / total_chars
            turn_duration = duration * share
            timeline.append(
                {"speaker": turn["speaker"], "start": cursor, "end": cursor + turn_duration}
            )
            cursor += turn_duration
        offset += duration
    return timeline, offset


def _find_active_turn(timeline: list[dict], t: float) -> dict | None:
    for turn in timeline:
        if turn["start"] <= t < turn["end"]:
            return turn
    return None


def _draw_avatar(diameter: int, color: tuple, mouth_open: bool, active: bool) -> Image.Image:
    img = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    ring_color = ACTIVE_RING_COLOR if active else IDLE_RING_COLOR
    draw.ellipse([2, 2, diameter - 2, diameter - 2], outline=ring_color, width=8)

    margin = diameter * 0.08
    draw.ellipse([margin, margin, diameter - margin, diameter - margin], fill=color)

    eye_y = diameter * 0.40
    eye_r = diameter * 0.035
    for eye_x in (diameter * 0.38, diameter * 0.62):
        draw.ellipse(
            [eye_x - eye_r, eye_y - eye_r, eye_x + eye_r, eye_y + eye_r], fill=(255, 255, 255)
        )

    mouth_cx, mouth_cy = diameter * 0.5, diameter * 0.62
    if mouth_open:
        draw.ellipse(
            [mouth_cx - diameter * 0.09, mouth_cy - diameter * 0.07,
             mouth_cx + diameter * 0.09, mouth_cy + diameter * 0.07],
            fill=MOUTH_COLOR,
        )
    else:
        draw.line(
            [mouth_cx - diameter * 0.09, mouth_cy, mouth_cx + diameter * 0.09, mouth_cy],
            fill=MOUTH_COLOR, width=6,
        )
    return img


def _compose_frame(title_text: str, speaker_states: dict, name_font, title_font) -> Image.Image:
    width, height = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    frame = Image.new("RGB", (width, height), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(frame)

    _draw_centered_in_box(draw, title_text, title_font, 0, width, 50, TEXT_COLOR)

    names = list(config.SPEAKERS.keys())
    slot_width = width / len(names)
    avatar_y = height / 2 - AVATAR_DIAMETER / 2 + 20

    for i, name in enumerate(names):
        info = config.SPEAKERS[name]
        state = speaker_states[name]
        avatar_img = _draw_avatar(AVATAR_DIAMETER, info["color"], state["mouth_open"], state["active"])
        avatar_x = slot_width * i + (slot_width - AVATAR_DIAMETER) / 2
        frame.paste(avatar_img, (int(avatar_x), int(avatar_y)), avatar_img)
        _draw_centered_in_box(
            draw, name, name_font, slot_width * i, slot_width, avatar_y + AVATAR_DIAMETER + 20, TEXT_COLOR
        )

    return frame


def render_frames(
    timeline: list[dict], total_duration: float, frames_dir: Path, title_text: str
) -> int:
    frames_dir.mkdir(parents=True, exist_ok=True)
    title_font = _load_font(36)
    name_font = _load_font(30)

    total_frames = max(1, int(total_duration * config.VIDEO_FRAME_RATE))
    for frame_no in range(total_frames):
        t = frame_no / config.VIDEO_FRAME_RATE
        active_turn = _find_active_turn(timeline, t)

        speaker_states = {}
        for name in config.SPEAKERS:
            if active_turn is not None and active_turn["speaker"] == name:
                elapsed = t - active_turn["start"]
                mouth_open = int(elapsed / config.MOUTH_TOGGLE_SECONDS) % 2 == 0
                speaker_states[name] = {"active": True, "mouth_open": mouth_open}
            else:
                speaker_states[name] = {"active": False, "mouth_open": False}

        frame = _compose_frame(title_text, speaker_states, name_font, title_font)
        frame.save(frames_dir / f"frame_{frame_no:06d}.png")

    logger.info("動画フレームを %d 枚生成しました。", total_frames)
    return total_frames


def assemble_video(frames_dir: Path, mp3_path: Path, mp4_path: Path) -> None:
    mp4_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(config.VIDEO_FRAME_RATE),
        "-i", str(frames_dir / "frame_%06d.png"),
        "-i", str(mp3_path),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(mp4_path),
    ]
    logger.info("FFmpegでMP4動画を組み立てます。")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpegによるMP4生成に失敗しました:\n{result.stderr[-3000:]}")
    logger.info("MP4を書き出しました: %s", mp4_path)


def create_talking_avatar_video(
    chunks: list[list[dict]],
    wav_paths: list[Path],
    mp3_path: Path,
    mp4_path: Path,
    version: str,
    date_str: str,
) -> None:
    timeline, total_duration = build_turn_timeline(chunks, wav_paths)
    title_text = f"Claude Code {version} ({date_str})"

    with TemporaryDirectory(prefix="podcast_frames_") as tmp_dir:
        frames_dir = Path(tmp_dir)
        render_frames(timeline, total_duration, frames_dir, title_text)
        assemble_video(frames_dir, mp3_path, mp4_path)
