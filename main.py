# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# --- Gemini 2.0 Flash (最新・爆速) ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
# 重要: JSONモードを強制する設定を追加
generation_config = {
    "temperature": 0.2,
    "response_mime_type": "application/json",
}
ai_model = genai.GenerativeModel('gemini-2.0-flash', generation_config=generation_config)

# --- DB設定 ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./local_dev.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AnalysisRequest(BaseModel):
    item_name: str
    item_description: str

# (User, Channel, Item モデルは変更なし)
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True)
    channels = relationship("Channel", back_populates="owner")

class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String(100))
    owner = relationship("User", back_populates="channels")
    items = relationship("Item", back_populates="channel")

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"))
    title = Column(String(200))
    description = Column(Text)
    price = Column(Integer)
    status = Column(String(20), default="on_sale")
    merrec_category = Column(String(100))
    channel = relationship("Channel", back_populates="items")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if db.query(User).count() == 0:
        me = User(username="べにひこ")
        db.add(me)
        db.commit()
        db.refresh(me)
        ch1 = Channel(user_id=me.id, name="WithU専用 (彩花ちゃん推し)")
        ch2 = Channel(user_id=me.id, name="東大工学部 参考書")
        db.add_all([ch1, ch2])
        db.commit()
    db.close()

@app.post("/api/ai/analyze_item")
async def analyze_item(request: AnalysisRequest):
    print(f"--- AI分析開始: {request.item_name} ---")
    
    # プロンプト: JSONで明確な判定を要求する
    prompt = f"""
    あなたは厳格なフリマアプリの管理者です。
    ユーザーの入力内容を審査し、以下のJSON形式のみで回答してください。
    余計な挨拶やMarkdown記号は不要です。

    {{
        "suggested_channel": "チャンネル名 (WithU専用, 東大工学部, その他 から選択)",
        "is_valid": true または false (矛盾や規約違反がないか),
        "reason": "ユーザーに表示する判定理由やアドバイス",
        "contradiction_check": "矛盾の有無の詳細"
    }}

    商品名: {request.item_name}
    説明文: {request.item_description}
    """
    
    try:
        response = ai_model.generate_content(prompt)
        # JSONとして解析して返す
        result_json = json.loads(response.text)
        print("AI判定結果:", result_json)
        return result_json
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        # 万が一JSONパースに失敗した場合のフェイルセーフ
        return {
            "suggested_channel": "解析不能",
            "is_valid": False,
            "reason": "AIエラーが発生しました。もう一度試してください。",
            "contradiction_check": str(e)
        }