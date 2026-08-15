"""調査済み Claude Code バージョンの記録（重複調査のスキップ用）。"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_state(path: Path) -> dict:
    if not path.exists():
        logger.info("状態ファイルが存在しないため新規作成します: %s", path)
        return {"researched_versions": []}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("researched_versions", [])
    return data


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    logger.info("状態ファイルを更新しました: %s", path)


def mark_covered(state: dict, tag_name: str) -> None:
    if tag_name not in state["researched_versions"]:
        state["researched_versions"].append(tag_name)
