# 軽量なPythonイメージを使用
FROM python:3.11-slim

# 作業ディレクトリの設定
WORKDIR /app

# 依存関係のコピーとインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードをコピー
COPY . .

# ポート8080で起動（Cloud Runのデフォルト）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]