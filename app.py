# from flask import Flask, request, abort
import os
import pandas as pd
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# --- 環境変数取得 ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- シラバスデータ読み込み ---
CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "all_syllabus_with_overview.csv")
df = pd.read_csv(CSV_PATH).fillna("")

def format_syllabuses(df):
    return "---\n".join(
        f"科目名: {row['subject_name']}\n概要: {row['overview']}\n科目URL: {row['detail_url']}"
        for _, row in df.iterrows()
    )

formatted_syllabus = format_syllabuses(df)

# --- LangChain チェーン構築 ---
def create_chain():
    system_prompt = f"""
以下は大学のシラバス情報です。

{formatted_syllabus}

この情報を元に、ユーザーの質問に合いそうな授業をいくつか紹介してください。
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}")
    ])
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=GEMINI_API_KEY,
        stream=False
    )

    return prompt | llm

chain = create_chain()
chat_history = []  # 簡易チャット履歴（長期維持したい場合はセッションIDで管理が必要）

# --- LINE Webhookエンドポイント ---
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

# --- メッセージイベント処理 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text

    chat_history.append(HumanMessage(content=user_message))

    try:
        response = chain.invoke({
            "chat_history": chat_history,
            "question": user_message
        })

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response.content)
        )
    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"エラーが発生しました: {str(e)}")
        )
