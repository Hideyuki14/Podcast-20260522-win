"""話者・モデル・パス等の集約設定ファイル。"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
STATE_DIR = BASE_DIR / "state"
STATE_FILE = STATE_DIR / "researched_versions.json"

# 調査対象リポジトリ（GitHub Releases API、認証不要）
GITHUB_REPO_OWNER = "anthropics"
GITHUB_REPO_NAME = "claude-code"
GITHUB_RELEASES_PER_PAGE = 30

# Gemini モデル
# 2.5 flash / flash-lite は無料枠で Google Search grounding が利用可能（500 RPD 共有）。
# 3.1 flash-lite 系は無料枠に grounding クォータが無いため調査には使用しない。
RESEARCH_MODEL = "gemini-2.5-flash-lite"
RESEARCH_FALLBACK_MODEL = "gemini-2.5-flash"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_FALLBACK_MODEL = "gemini-3.1-flash-tts-preview"

# リトライ設定: 初回 + 60秒待機後の再試行1回（フォールバック側も同様に再試行する）
RETRY_ATTEMPTS = 2
RETRY_WAIT_SECONDS = 60

# TTS 関連
TTS_MAX_CHUNK_CHARS = 1800
# Gemini TTS の出力仕様（16bit PCM / 24kHz / モノラル）
TTS_SAMPLE_RATE = 24000
TTS_SAMPLE_WIDTH = 2
TTS_CHANNELS = 1

# 話者設定（Gemini TTS MultiSpeakerVoiceConfig と一致させる。colorは動画のアバター配色）
SPEAKERS = {
    "田中": {"gender": "male", "voice": "Charon", "color": (59, 130, 246)},
    "鈴木": {"gender": "female", "voice": "Aoede", "color": (236, 72, 153)},
}

# 台本の目安文字数（日本語ナレーションの標準的な読み上げ速度から5分程度になるボリューム）
SCRIPT_TARGET_CHAR_MIN = 1800
SCRIPT_TARGET_CHAR_MAX = 2400

# Google OAuth / Drive
OAUTH_SCOPE = "https://www.googleapis.com/auth/drive.file"
OAUTH_TOKEN_URI = "https://oauth2.googleapis.com/token"
DRIVE_ROOT_FOLDER_NAME = "Podcasts"

# 中間成果物ファイル名（固定）
RESEARCH_JSON_NAME = "research.json"
SCRIPT_JSON_NAME = "script.json"
CHUNK_WAV_PREFIX = "chunk_"
PODCAST_MP3_NAME = "podcast.mp3"

# 動画（発話中のキャラクターが口パクするアニメーション + 音声）
PODCAST_MP4_NAME = "podcast.mp4"
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_FRAME_RATE = 10  # 1秒あたりのフレーム枚数（口パクが見える最低限の滑らかさ）
MOUTH_TOGGLE_SECONDS = 0.15  # 発話中、この間隔で口の開閉を切り替える

# 環境変数名（GitHub Secrets と一致させる）
ENV_GEMINI_API_KEY = "GEMINI_API_KEY"
ENV_GOOGLE_CLIENT_ID = "GOOGLE_CLIENT_ID"
ENV_GOOGLE_CLIENT_SECRET = "GOOGLE_CLIENT_SECRET"
ENV_GOOGLE_REFRESH_TOKEN = "GOOGLE_REFRESH_TOKEN"
ENV_DATE_OVERRIDE = "DATE_OVERRIDE"
