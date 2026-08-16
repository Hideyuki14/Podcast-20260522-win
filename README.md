# 自分専用 Claude Code Podcast 生成システム

Claude Code の最新バージョンの変更点を毎日自動調査し、日本語の男女二人（田中・鈴木）が
解説する5分程度の Podcast を生成して、自分の Google Drive にアップロードする個人用システムです。
すべて無料枠（クレジットカード登録不要）で完結するように設計されています。

## 全体の流れ

```
毎日 JST 6:00 (GitHub Actions cron)
  1. GitHub Releases API で Claude Code の最新リリース一覧を取得
  2. まだ調査していない最新バージョンを選定（state/researched_versions.json で管理）
  3. Gemini (gemini-2.5-flash-lite) + Google Search Grounding でウェブ(X含む)を調査 -> research.json
  4. Gemini で日本語対話台本を生成 -> script.json
  5. Gemini TTS (gemini-2.5-flash-preview-tts, マルチスピーカー) で音声合成 -> chunk_*.wav
  6. FFmpeg(pydub) でWAVを結合しMP3化 -> podcast.mp3
  7. 静止画タイトルカード(Pillow)+音声をFFmpegで結合しMP4化 -> podcast.mp4
  8. Google Drive の "Podcasts/<バージョン>_<日付>/" フォルダに mp3・mp4・JSONをアップロード
  9. 調査済みバージョンとして記録し、成果物(JSON)をリポジトリにコミット
```

失敗した場合でも、その時点までに生成された成果物は `output/` に残り、GitHub Actions が
コミットします（音声ファイルは `.gitignore` により除外されます）。

## セットアップ手順（この順番で進めてください）

1. **ソースコードの作成**（完了 — このリポジトリ一式）
2. **Google Cloud / OAuth2.0 の設定**（あなたが手動で行う）
3. **GitHub リポジトリの作成と Secrets 登録**（あなたが手動で行う）
4. **git のインストールと commit/push**（Claude Code が最後に自動で行う）

順序を守る理由: Windows環境でgitが未インストールの場合、インストール後に
Claude Codeの再起動が必要になり、それ以前の作業が中断してしまうためです。

---

## 手順2: Google Cloud / OAuth2.0 の設定

### 2-1. Gemini API キーの取得（クレジットカード不要）

1. https://aistudio.google.com/apikey にアクセスし、Googleアカウントでログイン
2. 「Create API key」から新しいプロジェクトでAPIキーを発行
3. 発行された文字列を控えておく（→ GitHub Secret `GEMINI_API_KEY` に使用）

### 2-2. Google Cloud プロジェクトと OAuth 同意画面の設定

Google Drive へのアップロードには OAuth2.0 の refresh token が必要です。
**重要:** OAuth同意画面は必ず「本番環境（Production）」に公開してください。
「テスト」のままだと refresh token が **7日で失効** し、毎日の自動実行が止まります。

1. https://console.cloud.google.com/ で新規プロジェクトを作成（クレジットカード不要）
2. 「APIとサービス」→「有効なAPIとサービス」から **Google Drive API** を有効化
3. 「APIとサービス」→「OAuth同意画面」で
   - User Type: 外部（External）
   - アプリ情報を入力（アプリ名・サポートメール等、個人利用でOK）
   - スコープは追加不要（後述の通り drive.file をOAuth Playground側で指定します）
   - **公開ステータスを「本番環境」に変更**（テストユーザーのままにしない）

### 2-3. OAuth クライアント ID の作成

1. 「APIとサービス」→「認証情報」→「認証情報を作成」→「OAuthクライアントID」
2. アプリケーションの種類: **ウェブアプリケーション**
3. 「承認済みのリダイレクトURI」に以下を追加:
   ```
   https://developers.google.com/oauthplayground
   ```
4. 作成後に表示される **クライアントID** と **クライアントシークレット** を控えておく
   （→ GitHub Secret `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` に使用）

### 2-4. OAuth 2.0 Playground で refresh token を取得

1. https://developers.google.com/oauthplayground/ を開く
2. 右上の歯車アイコン（OAuth 2.0 configuration）をクリックし、
   - 「Use your own OAuth credentials」にチェック
   - 手順2-3で控えた Client ID / Client Secret を入力

   > **重要:** ここで自分のクライアント情報を使わずにPlayground既定の認証情報のまま進めると、
   > refresh token が **24時間で自動失効** します。必ず自分のクライアント情報を設定してください。

3. 左側の「Step 1」の入力欄（Input your own scopes）に以下のスコープを入力し、
   「Authorize APIs」をクリック:
   ```
   https://www.googleapis.com/auth/drive.file
   ```
4. Googleアカウントでログインし、アクセスを許可
5. 「Step 2」で「Exchange authorization code for tokens」をクリック
6. 表示された **Refresh token** を控えておく（→ GitHub Secret `GOOGLE_REFRESH_TOKEN` に使用）

`drive.file` スコープは「このアプリ自身が作成/開いたファイルのみ」にアクセスを限定する
最小権限スコープです。そのため、アップロード先の `Podcasts` フォルダは既存のものを探すのではなく、
初回実行時にアプリ自身が新規作成します。

---

## 手順3: GitHub リポジトリの作成と Secrets 登録

### 3-1. リポジトリの作成

1. GitHub上で新規リポジトリを作成
2. **公開設定は Public（パブリック）にしてください**
   （GitHub Actionsの無料枠がパブリックリポジトリでは無制限になるため）
3. このフォルダの中身一式をリポジトリにpushします（手順4でClaude Codeが実施）

### 3-2. GitHub Secrets の登録

リポジトリの `Settings` → `Secrets and variables` → `Actions` → `New repository secret` から、
**以下の順番で** 登録してください（他の値の取得に依存する項目があるため、この順序を推奨します）。

| 順番 | Secret名 | 値の取得元 |
|---|---|---|
| 1 | `GEMINI_API_KEY` | 手順2-1で取得したAPIキー |
| 2 | `GOOGLE_CLIENT_ID` | 手順2-3で取得したクライアントID |
| 3 | `GOOGLE_CLIENT_SECRET` | 手順2-3で取得したクライアントシークレット |
| 4 | `GOOGLE_REFRESH_TOKEN` | 手順2-4で取得したリフレッシュトークン |

Secret名は上記の通り固定です（`config.py` および `.github/workflows/podcast.yml` から
この名前で参照されます）。

---

## GitHub Actions の実行方法

ワークフロー名: **Daily Podcast Generation**（`.github/workflows/podcast.yml`）

### 定期実行

毎日 UTC 21:00（= JST 6:00）に自動実行されます（`cron: '0 21 * * *'`）。
無料枠内で完結するよう、1日1エピソードのみ生成します。

### 手動実行

1. GitHub上のリポジトリで「Actions」タブ → 「Daily Podcast Generation」を選択
2. 「Run workflow」をクリック
3. `date_override` に任意の日付文字列（例: `2026-08-16`）を入力すると、
   Driveフォルダ名や台本内の日付表記にその日付が使われます。未入力なら実行時点のJST日付を使用します。

---

## 中間成果物

| ファイル | 内容 | 保存先 |
|---|---|---|
| `output/research.json` | 調査結果（リリースノート・Web調査サマリー・出典） | git commit（JSONのため） |
| `output/script.json` | 対話台本（話者・発話内容） | git commit（JSONのため） |
| `output/chunk_*.wav` | TTSチャンクごとの音声 | ローカル/Actions実行環境のみ（`.gitignore`対象） |
| `output/title_card.png` | 動画用の静止画タイトルカード | ローカル/Actions実行環境のみ（`.gitignore`対象） |
| `output/podcast.mp3` | 最終的なPodcast音声 | ローカル/Actions実行環境のみ（`.gitignore`対象）＋ Google Drive |
| `output/podcast.mp4` | 静止画タイトルカード＋音声の動画版 | ローカル/Actions実行環境のみ（`.gitignore`対象）＋ Google Drive |

`state/researched_versions.json` は調査済みバージョンの一覧を保持し、次回実行時に
同じバージョンを再調査しないようスキップするために使われます。

## リトライ・フォールバックの仕組み

- API が一時的に利用不可（429/500/503）の場合、60秒待機して再試行します（各モデルにつき最大2回試行）。
- 通常モデルが2回とも失敗した場合、フォールバックモデルに切り替えます。
  フォールバック側も同様に60秒待機しながら2回まで試行します（1回で諦めません）。
  - 調査: `gemini-2.5-flash-lite` → （失敗時）`gemini-2.5-flash`
  - 音声合成: `gemini-2.5-flash-preview-tts` → （失敗時）`gemini-3.1-flash-tts-preview`
- 台本は1,800文字未満のまとまり（チャンク）に分割し、チャンクごとに1回のTTS API呼び出しで
  音声化します（発話1つごとに呼び出すわけではありません）。

## 話者設定

`config.py` にて集約管理しています。

| 話者 | 性別 | Gemini TTS Voice |
|---|---|---|
| 田中 | 男性 | `Charon` |
| 鈴木 | 女性 | `Aoede` |

## 注意事項

- OAuth同意画面は必ず「本番環境」に公開してください（テストのままだとrefresh tokenが7日で失効します）。
- GitHub Actionsの `permissions: contents: write` により、ワークフロー自身がリポジトリへ
  成果物(JSON)をコミット・プッシュします。
- `gh` CLIは使用しません。Secretsの登録はGitHubのWeb UIから手動で行ってください。
- MP4動画のタイトルカードの日本語表示には `fonts-noto-cjk`（GitHub Actions上でapt-getインストール）を使用しています。
