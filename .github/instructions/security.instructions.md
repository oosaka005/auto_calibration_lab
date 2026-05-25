---
description: >
  Use when reviewing or updating security-related configurations: Docker image versions,
  Git secrets management, credentials, network access, and data backup rules.
applyTo: "**"
---

# Information Security

## インターネット接続が発生するタイミング

以下の操作時のみインターネット接続が発生する。通常の実験運用（`docker compose up -d`）はオフラインで動作する。

| タイミング | 接続先 |
|---|---|
| `docker compose build` / `docker compose pull` | `ghcr.io`（MADSciイメージ）、Docker Hub（mongo, redis, postgres） |
| `uv pip install`（ビルド時） | PyPI（`devices/requirements.txt` に記載のライブラリ） |
| `git push` / `git pull` | GitHub |

---

## Dockerイメージのバージョン管理

- イメージタグは必ず `:latest` ではなく**具体的なバージョンを固定**すること。
- `Dockerfile` および `compose.yaml` の MADSci イメージは現在 `0.7.0` に固定済み。
- MADSciのバージョンを更新する際は、`Dockerfile` と `compose.yaml` の両方を同時に変更すること。

```
# Dockerfile
FROM ghcr.io/ad-sdl/madsci:0.7.0   ← バージョン固定

# compose.yaml（lab_manager）
image: ghcr.io/ad-sdl/madsci_dashboard:0.7.0   ← バージョン固定
```

- インフライメージ（`mongo:8.0`, `redis:7.4`, `postgres:17`）はメジャー・マイナーバージョン固定済みのため、`:latest` と同等の問題はない。

---

## Pythonライブラリの信頼性

- `devices/requirements.txt` に追加するライブラリは PyPI 公式パッケージのみを使用すること。
- パッケージ名のタイポ（typosquatting）に注意する。

---

## Git へのシークレット混入防止

以下のファイルは `.gitignore` で除外済みであり、**Git にコミットしてはならない**。

| ファイル/ディレクトリ | 内容 |
|---|---|
| `.env` | 環境固有のオーバーライド・シークレット |
| `.madsci/` | 実験データ（MongoDB, PostgreSQL, Redis, ログ） |

- `settings.yaml` はシークレットを含まない設計であり、Git 管理してよい。
- シークレット・パスワード類は必ず `.env` に記載し、コードに直書きしないこと。

---

## デフォルトパスワードについて

`compose.yaml` に記載されている PostgreSQL の認証情報はDocker内部でのみ使用される。

```yaml
- POSTGRES_USER=madsci
- POSTGRES_PASSWORD=madsci   ← Docker 内部通信専用
```

- この認証情報は Resource Manager が PostgreSQL に接続するためのもので、ユーザーが手動で入力する必要はない。
- `compose.yaml` は Git 管理されるため、**リポジトリを公開設定にしないこと**。
- 将来的に複数人が同一ネットワーク内でシステムを共有する場合は、パスワードを変更すること。

---

## ネットワークアクセス（Node REST API）

MADSci 0.7.0 の Node API（ポート 2000, 2001 等）はアプリケーションレベルの認証機能を持たない。

- **現在の運用（VPN経由）**: VPN にログインできる人のみがポートに到達できるため、ネットワーク境界での保護が有効。
- VPN なしで複数人が同一 LAN を共有する環境では、同一ネットワーク上の誰でも API 経由でハードウェアを操作できる点に注意すること。
- ネットワーク構成を変更する場合は、ファイアウォールルールでノードのポートへのアクセスを制限すること。

---

## `.madsci/` データの取り扱い

`.madsci/` 以下には実験データとキャリブレーションデータが保存されており、**削除・上書きしたデータは元に戻せない**。

| データ | 保存先 | バックアップ対象 |
|---|---|---|
| キャリブレーションパラメータ | `.madsci/postgresql/` | **必須** |
| 実験データ | `.madsci/mongodb/` | 推奨 |
| ログ | `.madsci/logs/` | 任意 |

**バックアップルール**:
- 重要なキャリブレーション結果を書き込んだ後は、必ずバックアップを取ること。
- MADSci の組み込みバックアップツールを使用する。

```bash
# PostgreSQL（キャリブレーションデータ）
madsci-backup create --db-url postgresql://localhost:5432/madsci_resources

# MongoDB（実験データ）
madsci-backup create --db-url mongodb://localhost:27017
```
