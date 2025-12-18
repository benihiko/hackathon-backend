from fastapi import FastAPI

# FastAPIのインスタンスを作成
app = FastAPI()

# ルートURL (/) にアクセスしたときの処理
@app.get("/")
def read_root():
    return {"message": "Hello World from FastAPI on Cloud Run!"}

# /hello にアクセスしたときの処理 (おまけ)
@app.get("/hello")
def say_hello():
    return {"message": "こんにちわんこそば！ (Dockerized!)"}

# 以下の行はデプロイ時には不要ですが、ローカルでの実行確認用として参考になります
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)
