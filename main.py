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

# --- カテゴリ定義 (内部コード: 日本語表示名) ---
CATEGORY_TRANSLATION = {
    # --- 既存互換（レコメンドが効くエリア） ---
    "accessories.bag": "バッグ",
    "accessories.wallet": "財布・小物",
    "apparel.costume": "コスプレ・衣装",
    "apparel.dress": "ドレス・ワンピース",
    "apparel.jacket": "ジャケット・アウター",
    "apparel.jeans": "デニム・ジーンズ",
    "apparel.shirt": "シャツ・ブラウス",
    "apparel.shoes": "靴・シューズ",
    "apparel.shoes.sneakers": "スニーカー", # 既存リストに合わせて調整
    "apparel.tshirt": "Tシャツ・カットソー",
    "appliances.environment.air_conditioner": "エアコン",
    "appliances.kitchen.coffee_machine": "コーヒーメーカー",
    "appliances.kitchen.microwave": "電子レンジ",
    "appliances.kitchen.refrigerators": "冷蔵庫",
    "appliances.personal.hair_dryer": "ドライヤー",
    "appliances.personal.massager": "美容・健康家電", # 簡潔に
    "computers.notebook": "ノートPC",
    "computers.peripherals.monitor": "モニター",
    "electronics.audio.headphone": "ヘッドフォン",
    "electronics.camera.photo": "カメラ",
    "electronics.smartphone": "スマートフォン",
    "electronics.tablet": "タブレット",
    "electronics.video.tv": "テレビ",
    "furniture.living_room.sofa": "ソファ",
    "furniture.living_room.table": "テーブル",
    "kids.toys": "おもちゃ",
    "sport.bicycle": "自転車",
    
    # --- ★新規拡充エリア（ここから下を追加） ---
    
    # エンタメ・ホビー
    "hobby.idol_goods": "アイドルグッズ",
    "hobby.anime_goods": "アニメ・コミックグッズ",
    "hobby.trading_cards": "トレーディングカード",
    "hobby.figures": "フィギュア",
    "hobby.musical_instruments": "楽器・機材",
    "hobby.art": "美術品・アート",
    
    # 書籍・メディア
    "books.comic": "漫画・コミック",
    "books.novel": "小説・文学",
    "books.business": "ビジネス・経済",
    "books.study_guide": "参考書・学習本",
    "books.magazine": "雑誌",
    "media.cd": "CD",
    "media.dvd_bluray": "DVD/Blu-ray",
    "media.game_software": "ゲームソフト",
    "media.game_console": "ゲーム機本体",

    # メンズ・レディース詳細
    "fashion.mens.tops": "メンズトップス",
    "fashion.mens.bottoms": "メンズパンツ",
    "fashion.ladies.tops": "レディーストップス",
    "fashion.ladies.skirt": "スカート",
    
    # その他
    "tickets": "チケット",
    "food": "食品・お菓子",
    "handmade": "ハンドメイド",
    "other": "その他"
}


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
    
    # ★修正: [:50]を削除して全件渡す & プロンプトを明確化
def predict_category_code(item_name: str):
    # ファイル読み込みをやめて、辞書のキーを使う
    categories = list(CATEGORY_TRANSLATION.keys())
    
    # AIへの選択肢として英語コードを渡す
    categories_str = ", ".join(categories)
    
    prompt = f"""
    You are an AI assistant that classifies products for a Japanese flea market app.
    Select the MOST appropriate category code from the list below based on the Item Name.
    
    Item Name: {item_name}
    
    Output Requirement:
    - Return ONLY the category code string from the list.
    - Example: "hobby.idol_goods"
    
    Category List:
    {categories_str}
    """
    
    try:
        response = text_model.generate_content(prompt)
        prediction = response.text.strip()
        
        # 予測されたコードが辞書にあるか確認
        if prediction in CATEGORY_TRANSLATION:
            return prediction
        
        # 部分一致で救済（AIが少し余計な文字をつけても拾えるように）
        for key in CATEGORY_TRANSLATION:
            if key in prediction: return key
            
        return "other" # 見つからない場合はその他
    except Exception as e:
        print(f"Category Prediction Error: {e}")
        return "other"

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

# ★追加: いいね切替API
@app.post("/api/items/{item_id}/like")
def toggle_like(item_id: int, req: PurchaseRequest, db: Session = Depends(get_db)):
    # 既にいいねしているか確認
    existing = db.query(Like).filter(Like.user_id == req.user_id, Like.item_id == item_id).first()
    
    if existing:
        # あれば削除 (いいね解除)
        db.delete(existing)
        db.commit()
        return {"liked": False}
    else:
        # なければ作成 (いいね登録)
        new_like = Like(user_id=req.user_id, item_id=item_id)
        db.add(new_like)
        db.commit()
        return {"liked": True}

# ★追加: いいね一覧取得API
@app.get("/api/users/{user_id}/likes")
def get_user_likes(user_id: int, db: Session = Depends(get_db)):
    # Likeテーブル経由でItemを取得
    items = db.query(Item).join(Like).filter(Like.user_id == user_id).order_by(Like.created_at.desc()).all()
    
    # 辞書型に変換（共通処理）
    result = []
    for item in items:
        seller_name = "不明"
        if item.channel and item.channel.owner:
            seller_name = item.channel.owner.username
        
        jp_category_name = CATEGORY_TRANSLATION.get(item.category_code, item.category_code)
        
        result.append({
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "price": item.price,
            "image_data": item.image_data,
            "status": item.status,
            "category_code": item.category_code,
            "category_name": jp_category_name,
            "seller_name": seller_name
        })
    return result

# ★追加: 取引ページ用情報取得API
@app.get("/api/items/{item_id}/transaction")
def get_transaction(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item: raise HTTPException(status_code=404)
    
    seller = db.query(User).join(Channel).filter(Channel.id == item.channel_id).first()
    
    # ★追加: itemオブジェクトを辞書に変換し、日本語カテゴリを入れる
    jp_category_name = CATEGORY_TRANSLATION.get(item.category_code, item.category_code)
    
    item_dict = {
        "id": item.id,
        "title": item.title,
        "price": item.price,
        "image_data": item.image_data,
        "description": item.description,
        "category_name": jp_category_name # ★ここが重要！
    }
    
    return {
        "item": item_dict, # 生のitemではなく、辞書を返す
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
    
    # ★追加: 日本語カテゴリ名などを付与して辞書リストにする
    result = []
    for item in items:
        # 辞書から日本語名を取得
        jp_category_name = CATEGORY_TRANSLATION.get(item.category_code, item.category_code)
        
        result.append({
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "price": item.price,
            "image_data": item.image_data,
            "status": item.status,
            "category_code": item.category_code,
            "category_name": jp_category_name, # ★ここが重要！
        })
    return result

# ★修正: get_items (おすすめ計算にいいねを考慮)
# user_id 引数を追加 (Optional)
@app.get("/api/items")
def get_items(sort: str = "recommend", user_id: Optional[int] = None, db: Session = Depends(get_db)):
    items = db.query(Item).outerjoin(Channel).outerjoin(User).all()
    sorted_items_list = []

    if sort == "new":
        sorted_items_list = sorted(items, key=lambda x: x.id, reverse=True)
    else:
        # レコメンドロジック
        if rec_model is None or rec_prefs is None:
            sorted_items_list = sorted(items, key=lambda x: x.id, reverse=True)
        else:
            DEMO_USER_ID = 555696053 
            
            # ★追加: ユーザーがいいねしているカテゴリを取得して「ブースト」する
            liked_categories = []
            if user_id:
                liked_items = db.query(Item).join(Like).filter(Like.user_id == user_id).all()
                liked_categories = [i.category_code for i in liked_items if i.category_code]

            scored_items = []
            for item in items:
                user_cat_score = 0
                if item.category_code:
                    match = rec_prefs[(rec_prefs['user_id'] == DEMO_USER_ID) & (rec_prefs['category_code'] == item.category_code)]
                    if not match.empty: user_cat_score = match.iloc[0]['score']
                
                # ★追加: もしこの商品のカテゴリをいいねしていたら、スコアに +5.0点 (かなり強力)
                if item.category_code in liked_categories:
                    user_cat_score += 5.0

                try:
                    prob = rec_model.predict_proba(pd.DataFrame([[user_cat_score]], columns=['score']))[0][1]
                except: prob = 0
                scored_items.append({"item": item, "prob": prob})
            
            scored_items.sort(key=lambda x: x["prob"], reverse=True)
            sorted_items_list = [x["item"] for x in scored_items]

    # ... (結果の整形処理は既存と同じなので省略せず書くなら以下) ...
    result = []
    for item in sorted_items_list:
        seller_name = "不明"
        seller_id = -1
        if item.channel and item.channel.owner:
            seller_name = item.channel.owner.username
            seller_id = item.channel.owner.id
        jp_category_name = CATEGORY_TRANSLATION.get(item.category_code, item.category_code)
        
        result.append({
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "price": item.price,
            "image_data": item.image_data,
            "status": item.status,
            "category_code": item.category_code,
            "category_name": jp_category_name,
            "seller_id": seller_id,
            "seller_name": seller_name
        })
    return result


@app.get("/api/items/{item_id}/related")
def get_related(item_id: int, db: Session = Depends(get_db)):
    target = db.query(Item).filter(Item.id == item_id).first()
    if not target: return []
    return db.query(Item).filter(Item.category_code == target.category_code, Item.id != item_id).limit(3).all()