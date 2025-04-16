import os
import pickle
import base64
import requests
import re
import time
import json
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from flask import Flask, render_template, request
from datetime import datetime
from pytz import timezone
from flask_cors import CORS

# Khai báo phạm vi quyền truy cập Gmail API
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def gmail_authenticate():
    """Xác thực OAuth2 từ biến môi trường trên Heroku và cập nhật token nếu cần."""
    creds = None

    if "TOKEN_PICKLE" in os.environ:
        print("📌 Tìm thấy biến môi trường TOKEN_PICKLE, bắt đầu giải mã...")

        try:
            token_data = base64.b64decode(os.environ["TOKEN_PICKLE"])
            creds = pickle.loads(token_data)

            print("📌 Kiểm tra trạng thái token...")

            if not creds:
                print("❌ Không tạo được credentials từ token!")
                return None

            # Nếu token hết hạn và có refresh_token thì làm mới
            if creds.expired and creds.refresh_token:
                print("🔄 Token hết hạn, thử refresh...")
                creds.refresh(Request())
                print("✅ Token đã được làm mới!")

                # ➕ Cập nhật TOKEN_PICKLE mới lên Heroku
                try:
                    new_token_pickle = base64.b64encode(pickle.dumps(creds)).decode()
                    update_heroku_token(new_token_pickle)
                except Exception as e:
                    print(f"⚠️ Không thể cập nhật token mới lên Heroku: {e}")

            # Sau refresh mà vẫn không hợp lệ thì thoát
            if not creds.valid:
                print("❌ Token không hợp lệ ngay cả sau khi refresh!")
                return None

            print("✅ Xác thực Gmail API thành công!")
            return build("gmail", "v1", credentials=creds)

        except Exception as e:
            print(f"❌ Lỗi khi giải mã hoặc làm mới TOKEN_PICKLE: {e}")
            return None

    print("❌ Không tìm thấy biến môi trường TOKEN_PICKLE!")
    return None

def get_recent_unread_otp_emails():
    """Lấy email OTP từ TikTok trong 5 phút gần nhất và đánh dấu đã đọc."""
    service = gmail_authenticate()
    if service is None:
        print("⚠ Không thể xác thực Gmail API.")
        # Log lỗi chi tiết nếu cần
        app.logger.error("Token API không hợp lệ!")
        return "Token API bị lỗi, vui lòng liên hệ user 212078 - Anh Duy để được hỗ trợ.", 500

    otp_codes = []
    
    try:
        # Tính timestamp của 5 phút trước
        five_minutes_ago = int(time.time()) - 300
        query = f'from:register@account.tiktok.com is:unread after:{five_minutes_ago}'
        print(f"📌 Truy vấn Gmail với query: {query}")

        # Tìm email phù hợp
        results = service.users().messages().list(userId="me", q=query, maxResults=5).execute()
        messages = results.get("messages", [])

        if messages:
            print(f"✅ Tìm thấy {len(messages)} email OTP phù hợp trong 5 phút gần nhất!")

            for msg in messages:
                message = service.users().messages().get(userId="me", id=msg["id"]).execute()
                subject = ""

                for header in message["payload"]["headers"]:
                    if header["name"] == "Subject":
                        subject = header["value"]
                        break

                print(f"📩 Tiêu đề email: {subject}")

                # Tìm OTP trong tiêu đề email
                otp_match = re.search(r'\b\d{6}\b', subject)
                if otp_match:
                    otp_code = otp_match.group()
                    otp_codes.append(otp_code)
                    print(f"🔹 OTP tìm thấy: {otp_code}")

                # Đánh dấu email là đã đọc
                try:
                    service.users().messages().modify(
                        userId="me",
                        id=msg["id"],
                        body={"removeLabelIds": ["UNREAD"], "addLabelIds": []}
                    ).execute()
                    print(f"✅ Đã cập nhật email {msg['id']} thành 'Đã đọc'")
                except Exception as e:
                    print(f"❌ Lỗi khi cập nhật trạng thái email: {e}")

        return otp_codes

    except Exception as e:
        print(f"❌ Lỗi khi lấy OTP từ Gmail: {e}")
        return []

# Flask app
app = Flask(__name__)
CORS(app)  # Cho phép gọi API từ extension

# Biến toàn cục lưu lịch sử OTP
HISTORY_FILE = "/tmp/otp_history.json"

def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                # Kiểm tra nếu lịch sử là của hôm nay
                if data and data[0]["time"].startswith(datetime.now().strftime("%Y-%m-%d")):
                    return data
        return []
    except Exception as e:
        print(f"⚠️ Lỗi đọc file lịch sử: {e}")
        return []

def save_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception as e:
        print(f"⚠️ Lỗi ghi file lịch sử: {e}")

@app.route('/')
def index():
    return render_template("index.html", history=load_history())

@app.route('/process_otp', methods=['POST'])
def process_otp():
    # ⏰ Lấy giờ theo múi giờ Việt Nam
    vn_time = datetime.now(timezone("Asia/Ho_Chi_Minh"))
    timestamp = vn_time.strftime("%Y-%m-%d %H:%M:%S")
    
    history = load_history()

    try:
        otp_codes = get_recent_unread_otp_emails()

        if otp_codes:
            otp_message = f"🔹 Đã xử lý {len(otp_codes)} mã OTP: {', '.join(otp_codes)}"
        else:
            otp_message = "⚠ Không có email OTP mới trong 5 phút gần nhất."

    except Exception as e:
        otp_message = str(e)

    history.append({"time": timestamp, "result": otp_message})
    save_history(history)

    return otp_message

def update_heroku_token(new_token):
    """Gửi PATCH request lên Heroku để cập nhật TOKEN_PICKLE mới."""
    heroku_api_key = os.getenv("HEROKU_API_KEY")
    app_name = os.getenv("HEROKU_APP_NAME")
    if not heroku_api_key or not app_name:
        print("⚠️ HEROKU_API_KEY hoặc HEROKU_APP_NAME chưa được cấu hình.")
        return False

    url = f"https://api.heroku.com/apps/{app_name}/config-vars"
    headers = {
        "Accept": "application/vnd.heroku+json; version=3",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {heroku_api_key}"
    }

    data = {"TOKEN_PICKLE": new_token}

    response = requests.patch(url, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        print("✅ Đã cập nhật TOKEN_PICKLE mới lên Heroku thành công!")
        return True
    else:
        print(f"❌ Lỗi khi cập nhật TOKEN_PICKLE: {response.text}")
        return False

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
