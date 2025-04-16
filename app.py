import os
import re
import json
import time
import base64
import pickle
import requests
from datetime import datetime
from pytz import timezone
from flask import Flask, render_template, request
from flask_cors import CORS
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Khai báo phạm vi Gmail API
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Tạo Flask app
app = Flask(__name__)
CORS(app)

# File lưu lịch sử OTP
HISTORY_FILE = "/tmp/otp_history.json"

def gmail_authenticate():
    """Xác thực OAuth2 từ biến môi trường TOKEN_PICKLE và tự refresh nếu cần."""
    creds = None
    token_env = os.environ.get("TOKEN_PICKLE")

    if token_env:
        print("📌 Tìm thấy biến môi trường TOKEN_PICKLE, đang giải mã...")
        try:
            creds = pickle.loads(base64.b64decode(token_env))
            print("📌 Kiểm tra trạng thái token...")

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    print("🔄 Token hết hạn, đang làm mới...")
                    creds.refresh(Request())
                    print("✅ Token đã được làm mới!")

                    new_token_pickle = base64.b64encode(pickle.dumps(creds)).decode('utf-8')
                    update_heroku_token(new_token_pickle)
                else:
                    print("❌ Token không hợp lệ hoặc thiếu refresh_token.")
                    return None

            print("✅ Xác thực Gmail API thành công!")
            return build("gmail", "v1", credentials=creds)

        except Exception as e:
            print(f"❌ Lỗi khi giải mã hoặc làm mới token: {e}")
            return None
    else:
        print("❌ Không tìm thấy biến môi trường TOKEN_PICKLE!")
        return None

def update_heroku_token(new_token):
    """Cập nhật biến môi trường TOKEN_PICKLE mới lên Heroku."""
    api_key = os.getenv("HEROKU_API_KEY")
    app_name = os.getenv("HEROKU_APP_NAME")

    if not api_key or not app_name:
        print("⚠️ HEROKU_API_KEY hoặc HEROKU_APP_NAME chưa được cấu hình.")
        return False

    url = f"https://api.heroku.com/apps/{app_name}/config-vars"
    headers = {
        "Accept": "application/vnd.heroku+json; version=3",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response = requests.patch(url, headers=headers, json={"TOKEN_PICKLE": new_token})

    if response.status_code == 200:
        print("✅ Đã cập nhật TOKEN_PICKLE mới lên Heroku.")
        return True
    else:
        print(f"❌ Lỗi cập nhật TOKEN_PICKLE: {response.text}")
        return False

def get_recent_unread_otp_emails():
    """Lấy OTP từ email TikTok chưa đọc trong 5 phút gần nhất."""
    service = gmail_authenticate()
    if not service:
        app.logger.error("Token API không hợp lệ!")
        return "Token API lỗi, vui lòng liên hệ hỗ trợ.", 500

    otp_codes = []
    five_minutes_ago = int(time.time()) - 300
    query = f"from:register@account.tiktok.com is:unread after:{five_minutes_ago}"

    print(f"📌 Truy vấn Gmail với: {query}")

    try:
        results = service.users().messages().list(userId="me", q=query, maxResults=5).execute()
        messages = results.get("messages", [])

        if not messages:
            return []

        print(f"✅ Tìm thấy {len(messages)} email OTP.")

        for msg in messages:
            message = service.users().messages().get(userId="me", id=msg["id"]).execute()
            subject = next((h["value"] for h in message["payload"]["headers"] if h["name"] == "Subject"), "")

            print(f"📩 Tiêu đề: {subject}")
            match = re.search(r'\b\d{6}\b', subject)
            if match:
                otp = match.group()
                otp_codes.append(otp)
                print(f"🔹 OTP tìm thấy: {otp}")

            # Đánh dấu đã đọc
            service.users().messages().modify(
                userId="me",
                id=msg["id"],
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()

        return otp_codes

    except Exception as e:
        print(f"❌ Lỗi khi truy vấn Gmail: {e}")
        return []

def load_history():
    """Đọc lịch sử OTP từ file."""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                today = datetime.now().strftime("%Y-%m-%d")
                if data and data[0]["time"].startswith(today):
                    return data
        return []
    except Exception as e:
        print(f"⚠️ Lỗi đọc lịch sử: {e}")
        return []

def save_history(data):
    """Lưu lịch sử OTP vào file."""
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"⚠️ Lỗi ghi lịch sử: {e}")

@app.route("/")
def index():
    return render_template("index.html", history=load_history())

@app.route("/process_otp", methods=["POST"])
def process_otp():
    vn_time = datetime.now(timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
    history = load_history()

    try:
        otps = get_recent_unread_otp_emails()
        msg = f"🔹 Đã xử lý {len(otps)} mã OTP: {', '.join(otps)}" if otps else "⚠ Không có email OTP mới trong 5 phút gần nhất."
    except Exception as e:
        msg = f"❌ Lỗi xử lý OTP: {e}"

    history.append({"time": vn_time, "result": msg})
    save_history(history)

    return msg

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
