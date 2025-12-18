# hackathon-backend/main.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
import os
import json
import math
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# --- Gemini設定 ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
generation_config = {"temperature": 0.2, "response_mime_type": "application/json"}
# テキスト生成用モデル
ai_model = genai.GenerativeModel('gemini-2.0-flash', generation_config=generation_config)
# ベクトル化用モデル
embedding_model = "models/text-embedding-004"

# --- DB設定 (SQLite) ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./local_dev.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DBモデル定義 ---
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
    feature_vector = Column(Text, nullable=True) # AIベクトルを保存
    channel = relationship("Channel", back_populates="items")
    likes = relationship("Like", back_populates="item")

class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_id = Column(Integer, ForeignKey("items.id"))
    created_at = Column(DateTime, default=datetime.now)
    item = relationship("Item", back_populates="likes")

# --- アプリ初期化 ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 全許可
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    # デモ用データの作成
    db = SessionLocal()
    if db.query(User).count() == 0:
        me = User(username="べにひこ")
        db.add(me)
        db.commit()
        db.refresh(me)
        ch1 = Channel(user_id=me.id, name="メインチャンネル")
        db.add(ch1)
        db.commit()
    db.close()

# --- リクエスト型 ---
class AnalysisRequest(BaseModel):
    item_name: str
    item_description: str

class ItemCreate(BaseModel):
    title: str
    description: str
    price: int

# --- APIエンドポイント ---

# 1. AI出品診断
@app.post("/api/ai/analyze_item")
async def analyze_item(request: AnalysisRequest):
    print(f"AI分析: {request.item_name}")
    prompt = f"""
    フリマアプリの管理者として、以下のJSON形式のみで回答してください。
    {{
        "suggested_channel": "推奨チャンネル名",
        "is_valid": true または false,
        "reason": "判定理由",
        "contradiction_check": "矛盾チェック結果"
    }}
    商品名: {request.item_name}
    説明: {request.item_description}
    """
    try:
        response = ai_model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Error: {e}")
        return {"suggested_channel": "不明", "is_valid": False, "reason": "AIエラー", "contradiction_check": str(e)}

# 2. 商品一覧取得
@app.get("/api/items")
def get_items(db: Session = Depends(get_db)):
    return db.query(Item).order_by(Item.id.desc()).all()

# 3. 出品登録 (DB保存 + ベクトル化)
@app.post("/api/items")
def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    user = db.query(User).first() # デモ用ユーザー
    channel = db.query(Channel).filter(Channel.user_id == user.id).first()
    
    # AIベクトル計算
    vector_str = None
    try:
        embedding = genai.embed_content(
            model=embedding_model,
            content=item.title + " " + item.description,
            task_type="retrieval_document"
        )['embedding']
        vector_str = json.dumps(embedding)
    except Exception as e:
        print(f"ベクトル化失敗: {e}")

    new_item = Item(
        channel_id=channel.id,
        title=item.title,
        description=item.description,
        price=item.price,
        merrec_category="未分類",
        feature_vector=vector_str
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return {"message": "出品完了", "id": new_item.id}

# 4. レコメンド (類似商品)
@app.get("/api/items/{item_id}/related")
def get_related(item_id: int, db: Session = Depends(get_db)):
    target = db.query(Item).filter(Item.id == item_id).first()
    if not target or not target.feature_vector: return []
    
    target_vec = json.loads(target.feature_vector)
    results = []
    
    for item in db.query(Item).filter(Item.id != item_id).all():
        if item.feature_vector:
            vec = json.loads(item.feature_vector)
            # コサイン類似度計算
            dot = sum(a*b for a, b in zip(target_vec, vec))
            norm_a = math.sqrt(sum(a*a for a in target_vec))
            norm_b = math.sqrt(sum(b*b for b in vec))
            score = dot / (norm_a * norm_b) if norm_a * norm_b > 0 else 0
            results.append((score, item))
            
    results.sort(key=lambda x: x[0], reverse=True)
    return [item for score, item in results[:3]]