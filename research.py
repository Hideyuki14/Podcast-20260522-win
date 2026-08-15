"""Claude Code の最新バージョン変更点を調査するモジュール。

- リリース情報: GitHub Releases API（認証不要）
- 深掘り調査: Gemini + Google Search Grounding（X/Twitter含むウェブ公開情報を検索）
"""

import logging

import requests
from google import genai
from google.genai import types

import config
from retry_utils import call_with_fallback

logger = logging.getLogger(__name__)


def get_github_releases() -> list[dict]:
    url = f"https://api.github.com/repos/{config.GITHUB_REPO_OWNER}/{config.GITHUB_REPO_NAME}/releases"
    logger.info("GitHub Releases API から最新リリース一覧を取得します: %s", url)
    resp = requests.get(
        url,
        params={"per_page": config.GITHUB_RELEASES_PER_PAGE},
        headers={"Accept": "application/vnd.github+json"},
        timeout=30,
    )
    resp.raise_for_status()
    releases = resp.json()
    logger.info("リリースを %d 件取得しました。", len(releases))
    return releases


def pick_target_release(releases: list[dict], covered_versions: list[str]) -> tuple[dict | None, bool]:
    """未調査のうち最新のリリースを選ぶ。全て調査済みなら最新リリースを再訪(is_revisit=True)として返す。"""
    if not releases:
        return None, False
    sorted_releases = sorted(releases, key=lambda r: r["published_at"], reverse=True)
    for release in sorted_releases:
        if release["tag_name"] not in covered_versions:
            logger.info("未調査の最新バージョンを選定しました: %s", release["tag_name"])
            return release, False
    latest = sorted_releases[0]
    logger.warning(
        "直近のリリースは全て調査済みのため、最新バージョン %s を別角度で再調査します。",
        latest["tag_name"],
    )
    return latest, True


def _build_prompt(release: dict, is_revisit: bool) -> str:
    revisit_note = (
        "なお、このバージョンは以前に一度調査済みです。前回とは異なる切り口（コミュニティの反応の深掘り、"
        "実際の利用事例、開発者の評価など）で追加調査してください。\n"
        if is_revisit
        else ""
    )
    return f"""あなたはPodcast番組のリサーチャーです。以下のClaude Codeのリリース情報について、
ウェブ検索（X/Twitterの公開投稿を含む）を用いて深く調査し、日本語で詳細なリサーチメモを作成してください。

## リリース情報
- バージョン: {release.get('tag_name')}
- 公開日時: {release.get('published_at')}
- リリースノート:
{release.get('body') or '（本文なし）'}

{revisit_note}
## 調査してほしい観点
1. このバージョンの変更点の技術的な背景や意図
2. X（旧Twitter）や開発者コミュニティでの反応・評判・議論
3. 実際にどのように使われているか、具体的なユースケース
4. 前バージョンからの変化や、今後への示唆

Podcastの台本の元ネタとして使えるよう、具体的なエピソードや意見を交えて、
800〜1200文字程度の読み物として日本語でまとめてください。推測ではなく検索結果に基づいて記述してください。
"""


def research_version(client: genai.Client, release: dict, is_revisit: bool) -> dict:
    prompt = _build_prompt(release, is_revisit)

    def build_fn(model: str):
        def _call():
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            if not response.text:
                raise ValueError("Geminiからの調査結果が空でした。")
            return response

        return _call

    response = call_with_fallback(
        "research",
        build_fn(config.RESEARCH_MODEL),
        build_fn(config.RESEARCH_FALLBACK_MODEL),
        config.RETRY_ATTEMPTS,
        config.RETRY_WAIT_SECONDS,
    )

    sources = []
    try:
        candidate = response.candidates[0]
        grounding_metadata = getattr(candidate, "grounding_metadata", None)
        chunks = getattr(grounding_metadata, "grounding_chunks", None) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web is not None:
                sources.append({"title": web.title, "url": web.uri})
    except (IndexError, AttributeError) as exc:
        logger.warning("grounding_metadataの取得に失敗しました（無視して続行します）: %s", exc)

    return {
        "version": release.get("tag_name"),
        "release_name": release.get("name"),
        "published_at": release.get("published_at"),
        "release_url": release.get("html_url"),
        "release_notes": release.get("body"),
        "is_revisit": is_revisit,
        "summary": response.text,
        "sources": sources,
    }
