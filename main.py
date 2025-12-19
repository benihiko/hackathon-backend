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
from typing import List, Optional # ★追加

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
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    channel = relationship("Channel", back_populates="items")
    likes = relationship("Like", back_populates="item")

class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_id = Column(Integer, ForeignKey("items.id"))
    created_at = Column(DateTime, default=datetime.now)
    item = relationship("Item", back_populates="likes")

class PurchaseRequest(BaseModel):
    user_id: int

class AnalysisRequest(BaseModel):
    item_name: str
    item_description: str
    existing_channels: List[str] = [] # ユーザーが持っているチャンネル名のリスト

class ChannelCreate(BaseModel):
    name: str
    user_id: int

class ItemCreate(BaseModel):
    title: str
    description: str
    price: int
    image_data: str = ""
    user_id: int
    channel_id: int # ★修正: ユーザーが選択したチャンネルIDを必須にする

# --- アプリ ---
app = FastAPI()
#origins = [
#    "http://localhost:3000",
#    "https://hackathon-frontend-h3av.vercel.app", # ←ここをあなたの実際のVercel URLに変えてください！

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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

# ★追加: 購入API
@app.post("/api/items/{item_id}/purchase")
def purchase_item(item_id: int, req: PurchaseRequest, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="商品が見つかりません")
    
    if item.status == "sold":
        raise HTTPException(status_code=400, detail="この商品は既に売り切れています")
    
    # ステータス更新と購入者記録
    item.status = "sold"
    item.buyer_id = req.user_id
    db.commit()
    
    return {"message": "購入完了", "transaction_id": item.id}

# ★追加: 取引ページ用情報取得API
@app.get("/api/items/{item_id}/transaction")
def get_transaction(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item: raise HTTPException(status_code=404)
    
    # 出品者（チャンネルのオーナー）を取得
    seller = db.query(User).join(Channel).filter(Channel.id == item.channel_id).first()
    
    return {
        "item": item,
        "seller_name": seller.username if seller else "不明なユーザー"
    }

# ★追加: ユーザーのチャンネル一覧取得
@app.get("/api/users/{user_id}/channels")
def get_user_channels(user_id: int, db: Session = Depends(get_db)):
    return db.query(Channel).filter(Channel.user_id == user_id).all()

# ★追加: 新規チャンネル作成
@app.post("/api/channels")
def create_channel(req: ChannelCreate, db: Session = Depends(get_db)):
    new_ch = Channel(user_id=req.user_id, name=req.name)
    db.add(new_ch)
    db.commit()
    db.refresh(new_ch)
    return new_ch


@app.post("/api/ai/analyze_item")
async def analyze_item(request: AnalysisRequest):
    channels_str = ", ".join(request.existing_channels) if request.existing_channels else "なし"
    # ★修正: 「無関係なキーワードの羅列」を厳しくチェックするプロンプトに変更
    prompt = f"""
    You are a strict moderator for a flea market app.
    
    Task 1: Check for violations (Keyword Stuffing, Mismatches, Prohibited Items).
    Task 2: Select the best fit channel from the user's EXISTING CHANNELS list.
    
    User's Existing Channels: [{channels_str}]

    Item Name: {request.item_name}
    Description: {request.item_description}

    Output JSON keys must be exactly:
    - "is_valid": (Boolean) true if Safe, false if Violation
    - "reason": (String) Reason for judgment (Japanese).
    - "suggested_channel": (String) The EXACT name of the best matching channel from the list above. If none fit or list is empty, return "null" (string).
    - "new_channel_suggestion": (String) A recommended name for a NEW channel (e.g. "スニーカー", "家電") if existing ones don't fit.
    """
    try:
        response = ai_model.generate_content(prompt)
        # マークダウン記法の除去
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        print(f"AI Error: {e}")
        return {"suggested_channel": "不明", "is_valid": False, "reason": "AIエラーが発生しました", "new_channel_suggestion": "その他"}

@app.post("/api/items")
def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    # 指定されたチャンネルが存在するか確認
    channel = db.query(Channel).filter(Channel.id == item.channel_id).first()
    if not channel:
        raise HTTPException(status_code=400, detail="無効なチャンネルIDです")

    cat_code = predict_category_code(item.title)
    
    new_item = Item(
        channel_id=item.channel_id, # ★ここが変わりました
        title=item.title, 
        description=item.description,
        price=item.price, 
        image_data=item.image_data, 
        category_code=cat_code
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
    items = db.query(Item).outerjoin(Channel).outerjoin(User).all()
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
    sorted_items_list = [x["item"] for x in scored_items]

    result = []
    for item in sorted_items_list:
        seller_name = "不明"
        seller_id = -1
        # Item -> Channel -> User と辿って出品者情報を取得
        if item.channel and item.channel.owner:
            seller_name = item.channel.owner.username
            seller_id = item.channel.owner.id
        
        result.append({
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "price": item.price,
            "image_data": item.image_data,
            "status": item.status,
            "category_code": item.category_code,
            "seller_id": seller_id,      # ★追加: 自分の商品か判定用
            "seller_name": seller_name   # ★追加: 表示用
        })
    
    return result


@app.get("/api/items/{item_id}/related")
def get_related(item_id: int, db: Session = Depends(get_db)):
    target = db.query(Item).filter(Item.id == item_id).first()
    if not target: return []
    return db.query(Item).filter(Item.category_code == target.category_code, Item.id != item_id).limit(3).all()