import google.generativeai as genai
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import Base, Item, Channel, User, get_db
import os
import random
from dotenv import load_dotenv

load_dotenv()

# DB接続 (main.pyの設定を利用)
# ※ main.pyのDATABASE_URLと同じ設定にしてください
DB_USER = "benihiko"
DB_PASS = "Hide-1213"
DB_HOST = "136.119.203.142"
DB_NAME = "hackathon"
DATABASE_URL = f"mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

# --- 大量デモデータ (カテゴリコードは最新版に対応) ---
# seed_merrec.py の demo_items 部分をこれに書き換え

demo_items = [
    # --- アイドルグッズ ---

    {
        "title": "TWICE ペンライト Candy Bong Z", 
        "desc": "ライブで一度使用しました。点灯確認済み。", 
        "price": 4500, 
        "cat": "hobby.idol_goods",
        "image": "https://static.mercdn.net/item/detail/orig/photos/m88766350388_1.jpg?1725501367" # ライブ会場
    },
    
    # --- 本・参考書 ---
    {
        "title": "チャート式 基礎からの数学I+A", 
        "desc": "青チャートです。書き込みありません。", 
        "price": 1000, 
        "cat": "books.study_guide",
        "image": "https://static.mercdn.net/item/detail/orig/photos/m86450029901_1.jpg?1705650964" # 本
    },
    {
        "title": "鬼滅の刃 全巻セット", 
        "desc": "1巻から23巻まで。一読したのみです。", 
        "price": 8000, 
        "cat": "books.comic",
        "image": "https://m.media-amazon.com/images/I/91%20UnLEr6UL.jpg" # コミック
    },

    # --- ガジェット ---
    {
        "title": "iPhone 12 64GB ホワイト", 
        "desc": "SIMフリー。バッテリー最大容量88%。", 
        "price": 45000, 
        "cat": "electronics.smartphone",
        "image": "https://img.musbi.net/images/7ab5f/d5/d52fb286718a27eff8ba80dcae86d63293ff078e.JPG?resize=1500" # iPhone
    },
    {
        "title": "AirPods Pro 第一世代", 
        "desc": "左耳のみ聞こえにくい時があります。", 
        "price": 8000, 
        "cat": "electronics.audio.headphone",
        "image": "https://assets.st-note.com/production/uploads/images/146521036/rectangle_large_type_2_28baa95236aa4be62b69531879c6bdbc.jpeg?width=1200" # イヤホン
    },

    # --- ファッション ---
    {
        "title": "NIKE AirForce1 27cm", 
        "desc": "定番の白です。数回履きました。", 
        "price": 8000, 
        "cat": "apparel.shoes.sneakers",
        "image": "https://auctions.c.yimg.jp/images.auctions.yahoo.co.jp/image/dr000/auc0508/users/64af40ccbb66dc9308bc0734772c9f7e2305f4f8/i-img1200x1200-1723863886748a6uxzw.jpg" # スニーカー
    },
    # --- ガジェット・家電 ---
    {
        "title": "M2 MacBook Air 13インチ", 
        "desc": "メモリ16GB、SSD 512GB。動画編集用に購入しましたが、デスクトップ移行のため出品します。充放電回数20回程度の美品です。", 
        "price": 138000, 
        "cat": "computers.notebook",
        "image": "https://wired.jp/app/uploads/2024/03/09141011/main_MacBook-Air-M3-Review-Featured-Gear.jpeg"
    },
    {
        "title": "Sony WH-1000XM5 ノイズキャンセリングヘッドホン", 
        "desc": "業界最高クラスのノイキャン性能です。飛行機での移動中に数回使用しました。ケース、ケーブル完備。", 
        "price": 32000, 
        "cat": "electronics.audio.headphone",
        "image": "https://cdn.mos.cms.futurecdn.net/skBVreU5KroYycebb5Kqa9.jpg"
    },
    {
        "title": "Logicool MX Master 3S", 
        "desc": "静音モデルのマウスです。非常に使いやすいですが、手に合わなかったため出品します。", 
        "price": 9500, 
        "cat": "computers.peripherals.monitor", # 便宜上
        "image": "https://terablog2020.com/wp-content/uploads/2022/06/IMG_20220627_213646-1.jpg"
    },
    {
        "title": "TOEIC L&Rテスト 出る単特急 金のフレーズ", 
        "desc": "最新版です。数ページにフリクションでの書き込みがありましたが、消去済みです。", 
        "price": 600, 
        "cat": "books.study_guide",
        "image": "https://static.mercdn.net/item/detail/orig/photos/m67177711386_1.jpg?1764382919"
    },
    {
        "title": "Nintendo Switch 有機ELモデル ホワイト", 
        "desc": "画面保護フィルムを貼っています。動作確認済み、初期化して発送します。付属品全て揃っています。", 
        "price": 31000, 
        "cat": "media.game_console",
        "image": "https://static.mercdn.net/item/detail/orig/photos/m35377851247_1.jpg?1765742050"
    }

]

# ループの中身も少し修正 (imageキーを使うように)
# ...

# ...
def seed_data():
    # ユーザーを確認 (いなければ作る)
    user = db.query(User).filter(User.username == "べにひこ").first()
    if not user:
        print("ユーザー「べにひこ」が見つかりません。先にmain.pyを実行してユーザーを作成してください。")
        return

    # チャンネルを確認
    channel = db.query(Channel).filter(Channel.user_id == user.id).first()
    if not channel:
        print("チャンネルが見つかりません。")
        return
    
    print(f"🚀 ユーザー: {user.username} (ID: {user.id}) のチャンネルに商品を追加します...")
    
    count = 0
    for data in demo_items:
        # すでに同じ商品があればスキップ (重複登録防止)
        exists = db.query(Item).filter(Item.title == data["title"]).first()
        if exists:
            print(f"スキップ: {data['title']} (登録済み)")
            continue

        # Item作成
        new_item = Item(
            channel_id=channel.id,
            title=data["title"],
            description=data["desc"],
            price=data["price"],
            category_code=data["cat"],
            image_data=data.get("image", ""), # 画像は空にしておけば、フロントエンドがランダム画像を表示してくれます
            status="on_sale"
        )
        db.add(new_item)
        count += 1

    db.commit()
    print(f"✅ 完了！ {count}個の商品を追加しました。")

if __name__ == "__main__":
    seed_data()