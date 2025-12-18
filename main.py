import os
import mysql.connector
from fastapi import FastAPI

app = FastAPI()

def get_db_connection():
    # ここが教材のGoコードに対応する部分です
    # 環境変数から設定を読み込みます
    connection = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PWD"),
        database=os.getenv("MYSQL_DATABASE")
    )
    return connection

@app.get("/")
def read_root():
    return {"message": "Hello World!"}

# DB接続テスト用のURL
@app.get("/test-db")
def test_db():
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "success", "message": "DB接続に成功しました！"}
    except Exception as e:
        return {"status": "error", "message": f"DB接続エラー: {str(e)}"}
