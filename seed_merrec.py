# seed_merrec.py
import google.generativeai as genai
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import Base, Item, Channel, User
import os
import json
from dotenv import load_dotenv

load_dotenv()

# Gemini設定
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
# 埋め込みモデル（文章を数字に変えるモデル）
embedding_model = "models/text-embedding-004" 

# DB接続
SQLALCHEMY_DATABASE_URL = "sqlite:///./local_dev.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

# ダミーデータ (MerRec風)
merrec_data = [
    {"title": "NIKE スニーカー AirMax", "desc": "数回使用しました。27cmです。", "price": 8500, "cat": "Fashion"},
    {"title": "adidas ジャージ 上下", "desc": "黒地に白ライン。Lサイズ。", "price": 4000, "cat": "Fashion"},
    {"title": "iPhone 13 128GB", "desc": "画面割れなし。バッテリー85%。", "price": 60000, "cat": "Electronics"},
    {"title": "SONY ワイヤレスイヤホン", "desc": "ノイズキャンセリング機能付き。", "price": 12000, "cat": "Electronics"},
    {"title": "微分積分学の基礎", "desc": "大学1年生向けの数学の教科書です。", "price": 1500, "cat": "Books"},
    {"title": "線形代数入門", "desc": "東大出版会。書き込み少しあり。", "price": 1200, "cat": "Books"},
    {"title": "NiziU アヤカ トレカ", "desc": "Make you happy期のレアカードです。", "price": 3000, "cat": "Idol"},
    {"title": "NiziU ペンライト", "desc": "ライブで1回使用しました。点灯確認済み。", "price": 4500, "cat": "Idol"},
    {"title": "ポケモンカード ピカチュウ", "desc": "キラカードです。スリーブ保管。", "price": 5000, "cat": "Hobby"},
    {"title": "ワンピース 全巻セット", "desc": "1巻から100巻まで。日焼けあり。", "price": 15000, "cat": "Books"},
]

def get_embedding(text):
    # Geminiを使ってテキストをベクトル化
    result = genai.embed_content(
        model=embedding_model,
        content=text,
        task_type="retrieval_document",
        title="Item Description"
    )
    return result['embedding']

def seed_data():
    # ユーザーとチャンネルがあるか確認
    user = db.query(User).first()
    if not user:
        print("先にmain.pyを実行してユーザーを作成してください")
        return

    channel = db.query(Channel).filter(Channel.user_id == user.id).first()
    
    print("🚀 MerRecデータの注入を開始します...")
    
    for data in merrec_data:
        # すでに同じ商品があればスキップ
        exists = db.query(Item).filter(Item.title == data["title"]).first()
        if exists:
            print(f"スキップ: {data['title']}")
            continue

        print(f"ベクトル化中: {data['title']}...")
        # タイトルと説明文を合わせてベクトル化
        vector = get_embedding(data["title"] + " " + data["desc"])
        
        item = Item(
            channel_id=channel.id,
            title=data["title"],
            description=data["desc"],
            price=data["price"],
            merrec_category=data["cat"],
            feature_vector=json.dumps(vector) # 配列を文字列として保存
        )
        db.add(item)
    
    db.commit()
    print("✅ データ注入完了！")

if __name__ == "__main__":
    seed_data()