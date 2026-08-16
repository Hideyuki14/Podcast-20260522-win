"""静止画タイトルカード + 音声からMP4動画を生成するモジュール（FFmpeg利用）。"""

import logging
import subprocess
from pathlib import Path

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
ACCENT_COLOR = (147, 197, 253)


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


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, font, y: float, width: int, fill) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    draw.text(((width - text_width) / 2, y), text, font=font, fill=fill)


def create_title_card(image_path: Path, version: str, date_str: str) -> None:
    width, height = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    img = Image.new("RGB", (width, height), color=BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    title_font = _load_font(64)
    version_font = _load_font(40)
    speaker_font = _load_font(30)

    _draw_centered(draw, "自分専用 Claude Code Podcast", title_font, height / 2 - 150, width, TEXT_COLOR)
    _draw_centered(draw, f"{version}  ({date_str})", version_font, height / 2 - 20, width, ACCENT_COLOR)
    _draw_centered(draw, "田中 × 鈴木", speaker_font, height / 2 + 60, width, TEXT_COLOR)

    image_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(image_path)
    logger.info("タイトルカード画像を作成しました: %s", image_path)


def create_video(image_path: Path, mp3_path: Path, mp4_path: Path) -> None:
    mp4_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-i", str(mp3_path),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(mp4_path),
    ]
    logger.info("FFmpegでMP4動画を生成します。")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpegによるMP4生成に失敗しました:\n{result.stderr[-3000:]}")
    logger.info("MP4を書き出しました: %s", mp4_path)
