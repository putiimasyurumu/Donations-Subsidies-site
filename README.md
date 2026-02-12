# Donations-Subsidies-site

このリポジトリで実施した直近の修正内容をまとめています。

## 実施した修正

1. `jQuery` をローカル配置して読み込み追加
- 追加ファイル: `jquery.min.js`（`main.js` と同じディレクトリ）
- 変更ファイル: `index.html`
- 変更内容: `main.js` の前に `jquery.min.js` を読み込むように更新

2. MySQL接続ユーザー設定（`kifukin_user`）
- DB: `donation`（存在しなければ作成）
- ユーザー: `kifukin_user@127.0.0.1`
- 権限: `donation.*` に対する権限付与
- 反映ファイル: `donation/.env`
  - `DB_HOST=127.0.0.1`
  - `DB_PORT=3306`
  - `DB_USER=kifukin_user`
  - `DB_PASSWORD=<生成したパスワード>`
  - `DB_NAME=donation`

3. `app.py` のDBデフォルト値更新
- 変更ファイル: `donation/app.py`
- 変更内容:
  - `DB_HOST` デフォルトを `127.0.0.1`
  - `DB_USER` デフォルトを `kifukin_user`
  - `DB_NAME` デフォルトを `donation`

4. DB確認用APIの追加
- 変更ファイル: `donation/app.py`
- 追加エンドポイント: `GET /db-check`
- 確認内容:
  - DB接続可否
  - `DATABASE()` / `CURRENT_USER()` の取得
  - `donation_receipts` テーブル存在確認

## 動作確認コマンド

1. Flaskアプリ起動（例）
```bash
cd donation
python3 app.py
```

2. DB確認API
```bash
curl http://127.0.0.1:5000/db-check
```

3. Python構文チェック
```bash
python3 -m py_compile donation/app.py
```
