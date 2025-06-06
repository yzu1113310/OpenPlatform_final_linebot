from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import google.generativeai as genai
import json, os
from datetime import datetime
from flask import jsonify
import pandas as pd
import requests
from io import StringIO


GEMINI_API_KEY = 'AIzaSyCKvCEH9Eet14AacEBeYXJHJiNSjnyW5SU'
genai.configure(api_key=GEMINI_API_KEY)

# 建議使用 gemini-1.5-pro 或 gemini-1.5-flash，兩個都是支援 text 的
model = genai.GenerativeModel(model_name="gemini-1.5-flash")

app = Flask(__name__)

# 請把這兩個換成你 LINE Developers 後台的資料
LINE_CHANNEL_ACCESS_TOKEN = 'eCZ59rtmJXnbTQtHoWbLxt7O/AmEGOIsCEyD8GMNtedwCXv7YCLIWyegNMXzrTG3/SQ+fGoebTp1tWtKa1OyovBE9ZE7jUYCH+BBnFq7nYIcoCo+fDDtfVwFYg9Gjat6EeFuIce/jJrQJLwmpzFG6QdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '4512a2bd71b165e2e2a1e34598bcc6cd'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

HISTORY_FILE = "history.json"

user_mode = {}  # 記錄每位使用者目前的模式

COLLECT_PATH = "collections.json"

def load_collections():
    if os.path.exists(COLLECT_PATH):
        with open(COLLECT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_collections(data):
    with open(COLLECT_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

collections = load_collections()

def load_books_from_github(url):
    response = requests.get(url)
    response.encoding = 'utf-8'  # 若是中文內容，避免亂碼

    csv_data = StringIO(response.text)

    # 跳過第一行（時間戳），從第二行讀取 header
    df = pd.read_csv(csv_data, skiprows=1)
    df = df.head(100)  # 只取前 10 筆，加快速度
    return df 
    
def load_category(url):
    # 讀取 CSV（從 GitHub）
    response = requests.get(url)
    response.encoding = 'utf-8'  # 確保中文字正確
    df= pd.read_csv(StringIO(response.text))    
    df.columns = df.columns.str.replace('\ufeff', '').str.strip()

    # 取得最後一筆資料（最後一列）
    last_row = df.iloc[-1]

    # 顯示時間與分類排名資訊
    # timestamp = last_row['時間']
    categories = last_row.drop('時間')  # 移除時間欄位，只保留 Top1~Top20 

    print("欄位名稱列表：", df.columns.tolist())
    
    reply="排行榜分類：\n"
    for i, item in enumerate(categories):
        if pd.notna(item):
            reply+=f"Top{i+1}: {item}\n"

    return reply

def recommend_categories_by_ai(user_input):
    prompt = f"""
    請根據下列句子判斷使用者想看的書籍主題，推薦 1~3 個最合適的博客來分類，格式為：推薦分類：XXX、XXX、XXX。
    句子：「{user_input}」
    """
    response = model.generate_content(prompt)
    return response.text


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print("Error:", e)
        abort(400)

    return 'OK'



@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_msg = event.message.text.strip()
    print(f"使用者ID：{user_id}，訊息：{user_msg}")
    
    # 進入聊天模式
    if user_msg == "聊天":
        user_mode[user_id] = "chat"
        reply = "你已進入 AI 聊天模式，請開始聊天吧！\n\n輸入「退出」以退出聊天模式。"
    
    # 進入書籍模式
    elif user_msg == "書籍":
        user_mode[user_id] = "book"
        reply = (
                    "你已進入 書籍模式\n"
                    "請輸入以下指令查詢或操作：\n\n"
                    "🔸 「新書排行」：查看博客來最新熱門書籍\n"
                    "🔸 「分類」：查看受歡迎的書籍分類排行榜\n"
                    "🔸 「分類 XXX」：查詢特定分類的新書（如：分類 商業理財）\n"
                    "🔸 「收藏 書名」：將書籍加入收藏清單\n"
                    "🔸 「刪除收藏 書名」：從收藏清單移除指定書籍\n"
                    "🔸 「我的收藏」：查看目前收藏的所有書籍\n"
                    "❌ 輸入「退出」可離開書籍查詢模式，回到一般聊天\n\n"

                    "進入網站觀看更詳細圖表 :\n🔗 https://open-final.onrender.com/"
                )
    elif user_msg == "退出":
        user_mode.pop(user_id, None)
        reply = "你已退出目前模式。"
        
    
    # 處理聊天模式
    elif user_mode.get(user_id) == "chat":
        if user_msg.startswith('故事'):
            topic = user_msg[2:].strip()
            if topic:
                prompt = f"請寫一段主題為「{topic}」的小故事，100字以內。"
            else:
                prompt = "請寫一段有趣的小故事，字數控制在100字以內。"
            response = model.generate_content(prompt)
            reply = response.text
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply)
            )
        else:
            prompt = f"請用親切的語氣回覆以下訊息：「{user_msg}」"
            response = model.generate_content(prompt)
            reply = response.text
    
    # 處理書籍模式（這裡只是範例，可串 OpenLibrary 或 Google Books API）
    elif user_mode.get(user_id) == "book":
        # 書籍模式下處理查詢
        # keyword = user_msg
        df = load_books_from_github("https://raw.githubusercontent.com/allenwhitewho/s1111409_mid/main/static.csv")
        collections = load_collections()

        if user_msg == "新書排行":
            top = df.head(5)
            reply = "為您推薦以下書籍：\n"
            for _, row in top.iterrows():
                reply += f"\n《{row['書名']}》\n作者：{row['作者']}\n價格：{row['價格']}\n分類：{row['分類']}\n🔗 {row['連結']}\n"
        
        elif user_msg.startswith('分類'):
            if len(user_msg) == 2:
                reply=load_category("https://raw.githubusercontent.com/allenwhitewho/s1111409_mid/main/category_log.csv")
            else:
                keyword = user_msg[2:].strip()
                #print(keyword,"--------------------------")
                results = df[df['分類'].str.contains(keyword, na=False)]
                if results.empty:
                    reply = f"找不到分類包含「{keyword}」的新書。"
                else:
                    unique_books = results.drop_duplicates(subset='書名')
                    top = unique_books.head(5)  # 最多取 5 本
                    reply = f"為您找到 {len(top)} 本書：\n"
                    for _, row in top.iterrows():
                        reply += f"\n《{row['書名']}》\n作者：{row['作者']}\n價格：{row['價格']}\n分類：{row['分類']}\n🔗 {row['連結']}\n"
        
        elif user_msg == "每日一書":
            random_book = df.sample(1).iloc[0]
            prompt = f"請用簡短文字推薦這本書：《{random_book['書名']}》，作者是{random_book['作者']}。"
            response = model.generate_content(prompt)
            reply = f"📘 每日一書推薦：\n《{random_book['書名']}》\n作者：{random_book['作者']}\n分類：{random_book['分類']}\n AI推薦語：{response.text}\n\n🔗 {random_book['連結']}"

        elif user_msg.startswith("推薦"):
            user_input = user_msg[2:].strip()
            if not user_input:
                reply = "請輸入你最近的心情或想看的書的方向，例如：「推薦 我最近壓力很大」"
            else:
                # 使用 Gemini AI 取得分類建議
                category_response = recommend_categories_by_ai(user_input)
                print("AI回覆：", category_response)

                # 擷取推薦分類（可根據 AI 回傳的格式微調）
                categories = []
                if "推薦分類：" in category_response:
                    after_colon = category_response.split("推薦分類：")[-1]
                    categories = [c.strip() for c in after_colon.split("、")]

                if not categories:
                    reply = "無法理解你的需求，請再試一次描述喔！"
                else:
                    df = load_books_from_github("https://raw.githubusercontent.com/allenwhitewho/s1111409_mid/main/static.csv")
                    reply = "根據你的需求，推薦的分類如下：\n"

                    for cat in categories:
                        reply += f"\n【{cat}】\n"
                        matched = df[df['分類'].str.contains(cat, na=False)]
                        if matched.empty:
                            reply += "找不到相關書籍。\n"
                        else:
                            for _, row in matched.head(3).iterrows():
                                reply += f"《{row['書名']}》\n作者：{row['作者']}\n價格：{row['價格']}\n🔗 {row['連結']}\n\n"

        elif user_msg.startswith("收藏"):
            book_keyword = user_msg[2:].strip()
            if not book_keyword:
                reply = "請在「收藏」後面輸入要收藏的書名，例如：收藏 完全命中JLPT日檢文法"
            else:
                results = df[df['書名'].str.contains(book_keyword, na=False)]

                if results.empty:
                    reply = f"找不到書名包含「{book_keyword}」的書籍。"
                else:
                    top = results.iloc[0]  # 取第一筆符合的書
                    user_id = event.source.user_id

                    collections.setdefault(user_id, [])
                    already_saved = any(book['書名'] == top['書名'] for book in collections[user_id])

                    if already_saved:
                        reply = f"《{top['書名']}》已經在您的收藏中。"
                    else:
                        collections[user_id].append({
                            "書名": top['書名'],
                            "作者": top['作者'],
                            "價格": top['價格'],
                            "分類": top['分類'],
                            "連結": top['連結']
                        })
                        save_collections(collections)
                        reply = f"已成功收藏《{top['書名']}》。"

        elif user_msg == "我的收藏":
            user_id = event.source.user_id
            user_books = collections.get(user_id, [])

            if not user_books:
                reply = "您尚未收藏任何書籍。"
            else:
                reply = "📚 你的收藏書單：\n"
                for book in user_books:
                    reply += f"\n《{book['書名']}》\n作者：{book['作者']}\n價格：{book['價格']}\n🔗 {book['連結']}\n"

        elif user_msg.startswith("刪除收藏"):
            book_keyword = user_msg[4:].strip()
            if not book_keyword:
                reply = "已從您的收藏中刪除全部書籍。"
            else:
                user_id = event.source.user_id
                user_books = collections.get(user_id, [])

                new_list = [b for b in user_books if book_keyword not in b['書名']]
                if len(new_list) < len(user_books):
                    collections[user_id] = new_list
                    save_collections(collections)
                    reply = f"已從您的收藏中刪除包含「{book_keyword}」的書籍。"
                else:
                    reply = f"找不到包含「{book_keyword}」的收藏書籍。"      

    
        else:
            reply = (
                    "你已進入 書籍模式\n"
                    "請輸入以下指令查詢或操作：\n\n"
                    "🔸 「新書排行」：查看博客來最新熱門書籍\n"
                    "🔸 「分類」：查看受歡迎的書籍分類排行榜\n"
                    "🔸 「分類 XXX」：查詢特定分類的新書（如：分類 商業理財）\n"
                    "🔸 「收藏 書名」：將書籍加入收藏清單\n"
                    "🔸 「刪除收藏 書名」：從收藏清單移除指定書籍\n"
                    "🔸 「我的收藏」：查看目前收藏的所有書籍\n\n"
                    "❌ 輸入「退出」可離開書籍查詢模式，回到一般聊天"
                )

    # 尚未選擇模式
    else:
        reply = "請輸入「聊天」或「書籍」來開始使用對應的功能。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


# === 處理貼圖 ===
@handler.add(MessageEvent, message=StickerMessage)
def handle_sticker(event):
    package_id = event.message.package_id
    sticker_id = event.message.sticker_id
    reply = f"你傳了一個貼圖（package_id: {package_id}, sticker_id: {sticker_id}）"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )
    

# === 處理圖片 ===
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="你傳了一張圖片！")
    )

# === 處理影片 ===
@handler.add(MessageEvent, message=VideoMessage)
def handle_video(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="你傳了一部影片！")
    )

# === 處理位置 ===
@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    title = event.message.title or "地點"
    address = event.message.address
    lat = event.message.latitude
    lon = event.message.longitude
    reply = f"你傳來的位置：\n{title}\n地址：{address}\n座標：{lat}, {lon}"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

@app.route('/collection/<user_id>', methods=['GET'])
def get_collection(user_id):
    collections = load_collections()
    user_books = collections.get(user_id)
    if not user_books:
        return jsonify({"message": "找不到收藏書籍"}), 404
    return jsonify(user_books), 200

@app.route('/collections', methods=['GET'])
def get_all_collections():
    collections = load_collections()
    return jsonify(collections), 200

@app.route('/collection/<user_id>', methods=['DELETE'])
def delete_collection(user_id):
    collections = load_collections()
    if user_id in collections:
        del collections[user_id]
        save_collections(collections)
        return jsonify({"message": "已刪除該使用者的收藏資料"}), 200
    else:
        return jsonify({"message": "找不到該使用者的收藏資料"}), 404

'''
# ====== RESTful API：GET / DELETE ======
@app.route("/history/<user_id>", methods=['GET'])
def get_history(user_id):
    data = load_history()
    if user_id in data:
        return jsonify(data[user_id])
    return jsonify({"message": "沒有找到該使用者的紀錄"}), 404

@app.route("/history/<user_id>", methods=['DELETE'])
def delete_history(user_id):
    data = load_history()
    if user_id in data:
        del data[user_id]
        save_history(data)
        return jsonify({"message": f"{user_id} 的紀錄已刪除"}), 200
    else:
        return jsonify({"message": "沒有找到該使用者的紀錄"}), 404
'''

if __name__ == "__main__":
    app.run()
