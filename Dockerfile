# Pythonの軽量版イメージをベースにする
FROM python:3.11-slim

# 作業ディレクトリを /app に設定
WORKDIR /app

# FastAPIをインストール
# requirements.txt が不要なので、直接pip installします
RUN pip install fastapi uvicorn

# アプリケーションのコードをコンテナにコピー
COPY . .

# コンテナがリッスンするポート番号を指定 (Cloud Runは8080を期待します)
EXPOSE 8080

# アプリケーションを起動するコマンド
# uvicornを使ってmain.pyのappインスタンスをホスト0.0.0.0のポート8080で起動
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
