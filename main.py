# hackathon-backend/main.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.dialects.mysql import LONGTEXT 
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
from passlib.context import CryptContext # ★追加

load_dotenv()

# --- パスワードハッシュ化設定 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Gemini設定 ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
generation_config = {"temperature": 0.2, "response_mime_type": "application/json"}
ai_model = genai.GenerativeModel('gemini-2.0-flash', generation_config=generation_config)
text_model = genai.GenerativeModel('gemini-2.0-flash')

# --- モデル読み込み ---
try:
    print("学習済みモデルを読み込んでいます...")
    rec_data = joblib.load('recommender.pkl')
    rec_model = rec_data['model'] 
    rec_prefs = rec_data['prefs'] 
    print("モデル読み込み完了 ✅")
except Exception as e:
    print(f"モデル読み込み失敗: {e}")
    rec_model = None
    rec_prefs = None

try:
    with open("category_list.txt", "r", encoding="utf-8") as f:
        CATEGORY_MASTER = [line.strip() for line in f.readlines() if line.strip()]
except:
    CATEGORY_MASTER = []

# --- Cloud SQL接続設定 ---
DB_USER = "benihiko"
DB_PASS = "Hide-1213"
DB_HOST = "136.119.203.142"
DB_NAME = "hackathon"

DATABASE_URL = f"mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DBモデル ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True)
    hashed_password = Column(String(100)) # ★追加: パスワード保存用
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
    category_code = Column(String(100), nullable=True) 
    feature_vector = Column(Text, nullable=True)
    image_data = Column(LONGTEXT, nullable=True)
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
origins = [
    "http://localhost:3000",
    "https://hackathon-frontend-h3av.vercel.app/", # ←ここをあなたの実際のVercel URLに変えてください！
]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@app.on_event("startup")
def startup_event():
    try:
        # DB接続を試みる
        print("DB接続を開始します...")
        Base.metadata.create_all(bind=engine)
        print("DB接続成功")

        # デモユーザー作成など（もしあれば）
        db = SessionLocal()
        if db.query(User).filter(User.username == "べにひこ").count() == 0:
            me = User(username="べにひこ")
            db.add(me)
            db.commit()
            ch1 = Channel(user_id=me.id, name="メインチャンネル")
            db.add(ch1)
            db.commit()
        db.close()
    except Exception as e:
        # 重要：ここでエラーを握りつぶして、アプリの起動を止めないようにする
        print(f"★警告: DB接続に失敗しました。アプリは起動しますがDB機能は使えません。エラー内容: {e}")
        pass

# --- ロジック ---
def predict_category_code(item_name: str):
    if not CATEGORY_MASTER: return "unknown"
    prompt = f"リストの中から、この商品に最も近いカテゴリを1つ選び、その文字列だけを返してください。\n商品: {item_name}\nリスト: {', '.join(CATEGORY_MASTER[:50])}..."
    try:
        response = text_model.generate_content(prompt)
        prediction = response.text.strip()
        for cat in CATEGORY_MASTER:
            if cat in prediction: return cat
        return "unknown"
    except: return "unknown"

# --- API ---
class AnalysisRequest(BaseModel):
    item_name: str
    item_description: str

class ItemCreate(BaseModel):
    title: str
    description: str
    price: int
    image_data: str = ""
    user_id: int

# ★追加: ユーザー認証用モデル
class UserAuth(BaseModel):
    username: str
    password: str

# ★追加: 新規登録API
@app.post("/api/register")
def register(user_data: UserAuth, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="このユーザー名は既に使用されています")
    
    hashed_pw = pwd_context.hash(user_data.password)
    new_user = User(username=user_data.username, hashed_password=hashed_pw)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # チャンネルも自動作成
    default_ch = Channel(user_id=new_user.id, name="メインチャンネル")
    db.add(default_ch)
    db.commit()
    
    return {"id": new_user.id, "username": new_user.username, "message": "登録完了"}

# ★追加: ログインAPI
@app.post("/api/login")
def login(user_data: UserAuth, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_data.username).first()
    if not user or not user.hashed_password or not pwd_context.verify(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="ユーザー名かパスワードが間違っています")
    
    return {"id": user.id, "username": user.username, "message": "ログイン成功"}


@app.post("/api/ai/analyze_item")
async def analyze_item(request: AnalysisRequest):
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
    # リクエストで送られてきた user_id を使う
    user = db.query(User).filter(User.id == item.user_id).first()
    if not user:
        # 万が一ユーザーがいなければデモ用ユーザーにフォールバック
        user = db.query(User).first()
    
    channel = db.query(Channel).filter(Channel.user_id == user.id).first()
    # チャンネルがなければ作る
    if not channel:
        channel = Channel(user_id=user.id, name=f"{user.username}のチャンネル")
        db.add(channel)
        db.commit()
    
    cat_code = predict_category_code(item.title)
    
    new_item = Item(
        channel_id=channel.id, title=item.title, description=item.description,
        price=item.price, image_data=item.image_data, category_code=cat_code
    )
    db.add(new_item)
    db.commit()
    return {"message": "登録完了", "id": new_item.id}

@app.get("/api/users/{user_id}/items")
def get_user_items(user_id: int, db: Session = Depends(get_db)):
    # Channel経由でItemを取得
    items = db.query(Item).join(Channel).filter(Channel.user_id == user_id).order_by(Item.id.desc()).all()
    return items

@app.get("/api/items")
def get_items(db: Session = Depends(get_db)):
    items = db.query(Item).all()
    if rec_model is None or rec_prefs is None:
        return sorted(items, key=lambda x: x.id, reverse=True)

    DEMO_USER_ID = 555696053 
    scored_items = []
    
    for item in items:
        user_cat_score = 0
        if item.category_code:
            match = rec_prefs[(rec_prefs['user_id'] == DEMO_USER_ID) & (rec_prefs['category_code'] == item.category_code)]
            if not match.empty: user_cat_score = match.iloc[0]['score']
        
        try:
            prob = rec_model.predict_proba(pd.DataFrame([[user_cat_score]], columns=['score']))[0][1]
        except: prob = 0
        scored_items.append({"item": item, "prob": prob})
    
    scored_items.sort(key=lambda x: x["prob"], reverse=True)
    return [x["item"] for x in scored_items]

@app.get("/api/items/{item_id}/related")
def get_related(item_id: int, db: Session = Depends(get_db)):
    target = db.query(Item).filter(Item.id == item_id).first()
    if not target: return []
    return db.query(Item).filter(Item.category_code == target.category_code, Item.id != item_id).limit(3).all()