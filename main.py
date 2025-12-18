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
import joblib
import pandas as pd

load_dotenv()

# --- Gemini設定 ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
generation_config = {"temperature": 0.2, "response_mime_type": "application/json"}
ai_model = genai.GenerativeModel('gemini-2.0-flash', generation_config=generation_config)
# カテゴリ推論用はJSONモードを使わない
text_model = genai.GenerativeModel('gemini-2.0-flash')

# --- レコメンドモデルの読み込み ---
try:
    print("学習済みモデルを読み込んでいます...")
    rec_data = joblib.load('recommender.pkl')
    rec_model = rec_data['model'] # LogisticRegression
    rec_prefs = rec_data['prefs'] # ユーザーの好みデータ (DataFrame)
    print("モデル読み込み完了 ✅")
except Exception as e:
    print(f"モデル読み込み失敗 (レコメンド機能は制限されます): {e}")
    rec_model = None
    rec_prefs = None

# マスタカテゴリの読み込み
try:
    with open("category_list.txt", "r", encoding="utf-8") as f:
        CATEGORY_MASTER = [line.strip() for line in f.readlines() if line.strip()]
except:
    CATEGORY_MASTER = []

# --- DB設定 ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./local_dev.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DBモデル ---
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
    # ★重要: データ分析チーム指定のカラム
    category_code = Column(String(100), nullable=True) 
    feature_vector = Column(Text, nullable=True)
    image_data = Column(Text, nullable=True)
    channel = relationship("Channel", back_populates="items")
    likes = relationship("Like", back_populates="item")

class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_id = Column(Integer, ForeignKey("items.id"))
    created_at = Column(DateTime, default=datetime.now)
    item = relationship("Item", back_populates="likes")

# --- アプリ ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# --- ヘルパー関数: カテゴリ推論 ---
def predict_category_code(item_name: str):
    if not CATEGORY_MASTER: return "unknown"
    
    # AIへの指示
    prompt = f"""
    リストの中から、この商品に最も近いカテゴリを1つ選び、その文字列だけを返してください。
    リスト外の言葉は厳禁です。

    [商品名]
    {item_name}

    [リスト]
    {", ".join(CATEGORY_MASTER[:100])} ... (以下省略)
    """
    try:
        response = text_model.generate_content(prompt)
        prediction = response.text.strip()
        # マスタに存在するかチェック (完全一致検索)
        # ※簡易化のため、AIの回答がマスタに含まれていれば採用
        for cat in CATEGORY_MASTER:
            if cat in prediction:
                return cat
        return "unknown"
    except:
        return "unknown"

# --- API ---
class AnalysisRequest(BaseModel):
    item_name: str
    item_description: str

class ItemCreate(BaseModel):
    title: str
    description: str
    price: int
    image_data: str = ""

@app.post("/api/ai/analyze_item")
async def analyze_item(request: AnalysisRequest):
    # 既存の診断ロジック
    prompt = f"""
    フリマアプリ管理者としてJSONで回答。
    {{ "suggested_channel": "推奨チャンネル", "is_valid": true/false, "reason": "理由" }}
    商品: {request.item_name}, 説明: {request.item_description}
    """
    try:
        response = ai_model.generate_content(prompt)
        return json.loads(response.text)
    except:
        return {"suggested_channel": "不明", "is_valid": False, "reason": "AIエラー"}

@app.post("/api/items")
def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    user = db.query(User).first()
    channel = db.query(Channel).filter(Channel.user_id == user.id).first()
    
    # 1. 自動カテゴリ推論 (The Bridge)
    cat_code = predict_category_code(item.title)
    print(f"自動付与カテゴリ: {cat_code}")

    new_item = Item(
        channel_id=channel.id, title=item.title, description=item.description,
        price=item.price, image_data=item.image_data, 
        category_code=cat_code # ★AIが決めたカテゴリを保存
    )
    db.add(new_item)
    db.commit()
    return {"message": "登録完了", "id": new_item.id}

@app.get("/api/items")
def get_items(db: Session = Depends(get_db)):
    items = db.query(Item).all()
    
    # モデルが読み込めていない場合はID順で返す
    if rec_model is None or rec_prefs is None:
        return sorted(items, key=lambda x: x.id, reverse=True)

    # --- 本格レコメンドロジック ---
    # デモのため、特定ユーザー（電子機器好きのユーザーID）になりきってスコア計算する
    # 実際はログイン中の user.id を使う
    DEMO_USER_ID = 555696053 # electronics.clocks などを好むユーザー
    
    scored_items = []
    
    for item in items:
        # 1. このユーザーの、このカテゴリに対するスコアを取得
        user_cat_score = 0
        cat = item.category_code
        
        if cat:
            # prefs (DataFrame) から検索
            match = rec_prefs[(rec_prefs['user_id'] == DEMO_USER_ID) & (rec_prefs['category_code'] == cat)]
            if not match.empty:
                user_cat_score = match.iloc[0]['score']
        
        # 2. モデルで「購入確率」を予測
        # モデルへの入力は [[score]] という形のDataFrame
        try:
            input_df = pd.DataFrame([[user_cat_score]], columns=['score'])
            prob = rec_model.predict_proba(input_df)[0][1] # クラス1(購入)の確率
        except:
            prob = 0
            
        # 3. 確率をアイテムに紐付けてリスト化
        scored_items.append({"item": item, "prob": prob})
    
    # 4. 確率が高い順にソート
    scored_items.sort(key=lambda x: x["prob"], reverse=True)
    
    # アイテムオブジェクトだけを取り出して返す
    return [x["item"] for x in scored_items]

@app.get("/api/items/{item_id}/related")
def get_related(item_id: int, db: Session = Depends(get_db)):
    # 簡易レコメンド（同じカテゴリのものを返す）
    target = db.query(Item).filter(Item.id == item_id).first()
    if not target: return []
    
    related = db.query(Item).filter(
        Item.category_code == target.category_code, 
        Item.id != item_id
    ).limit(3).all()
    
    return related