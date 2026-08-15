"""Google Drive へのアップロードモジュール（OAuth2.0 refresh tokenで自動認証）。

スコープは drive.file のみを使用するため、このアプリ自身が作成したファイル/フォルダにしか
アクセスできない。そのため "Podcasts" フォルダは既存フォルダを探すのではなく、
未作成であればアプリ自身が作成する。
"""

import logging
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config

logger = logging.getLogger(__name__)


def get_drive_service(client_id: str, client_secret: str, refresh_token: str):
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri=config.OAUTH_TOKEN_URI,
        scopes=[config.OAUTH_SCOPE],
    )
    return build("drive", "v3", credentials=creds)


def _escape(name: str) -> str:
    return name.replace("'", "\\'")


def find_or_create_folder(service, name: str, parent_id: str | None = None) -> str:
    query = f"name = '{_escape(name)}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        logger.info("既存のDriveフォルダを使用します: %s (id=%s)", name, files[0]["id"])
        return files[0]["id"]

    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]
    folder = service.files().create(body=metadata, fields="id").execute()
    logger.info("Driveフォルダを新規作成しました: %s (id=%s)", name, folder["id"])
    return folder["id"]


def upload_file(service, local_path: Path, drive_name: str, parent_id: str, mime_type: str) -> str:
    metadata = {"name": drive_name, "parents": [parent_id]}
    media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=True)
    file = service.files().create(body=metadata, media_body=media, fields="id").execute()
    logger.info("Driveにアップロードしました: %s (id=%s)", drive_name, file["id"])
    return file["id"]


def upload_episode(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    dated_folder_name: str,
    files: list[tuple[Path, str]],
) -> None:
    """files: [(ローカルパス, MIMEタイプ), ...]"""
    service = get_drive_service(client_id, client_secret, refresh_token)
    root_id = find_or_create_folder(service, config.DRIVE_ROOT_FOLDER_NAME)
    episode_folder_id = find_or_create_folder(service, dated_folder_name, parent_id=root_id)

    for local_path, mime_type in files:
        upload_file(service, local_path, local_path.name, episode_folder_id, mime_type)
