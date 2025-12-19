# migrate.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import Item, Base  # main.pyからモデルを読み込む
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

# Gemini設定
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')

# DB接続
SQLALCHEMY_DATABASE_URL = "sqlite:///./local_dev.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

def load_categories():
    with open("category_list.txt", "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def predict_category(item_name, categories):
    # カテゴリリストを文字列化してプロンプトに埋め込む
    cat_str = "\n".join(categories)
    prompt = f"""
    以下の商品に最も適したカテゴリを、リストの中から1つだけ選んで返してください。
    余計な説明は不要です。リスト内の文字列そのものを返してください。

    [商品名]
    {item_name}

    [カテゴリリスト]
    {cat_str}
    """
    try:
        response = model.generate_content(prompt)
        prediction = response.text.strip()
        # 幻覚防止: リストに存在するか確認
        if prediction in categories:
            return prediction
        else:
            return "unknown"
    except Exception as e:
        print(f"Error: {e}")
        return "unknown"

def migrate():
    categories = load_categories()
    items = db.query(Item).filter((Item.category_code == None) | (Item.category_code == "")).all()
    
    print(f"対象アイテム数: {len(items)}件")
    
    for item in items:
        print(f"処理中: {item.title} ...", end=" ")
        cat = predict_category(item.title, categories)
        item.category_code = cat
        print(f"-> {cat}")
    
    db.commit()
    print("マイグレーション完了！")

if __name__ == "__main__":
    migrate()