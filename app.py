import os
import pickle
import base64
import requests
import re
import time
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from flask import Flask, render_template, request

# Khai báo phạm vi quyền truy cập Gmail API
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def gmail_authenticate():
    """Xác thực OAuth2 từ biến môi trường trên Heroku."""
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

            if creds.expired and creds.refresh_token:
                print("🔄 Token hết hạn, thử refresh...")
                creds.refresh(Request())
                print("✅ Token đã được làm mới!")

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
        return []

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

def send_line_notify(message):
    """Gửi OTP qua LINE Notify."""
    line_token = os.getenv("LINE_NOTIFY_TOKEN", "")

    if not line_token:
        print("⚠ Không tìm thấy LINE_NOTIFY_TOKEN trong biến môi trường!")
        return False

    headers = {"Authorization": f"Bearer {line_token}"}
    data = {"message": message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, data=data)

    if response.status_code == 200:
        print("✅ Đã gửi OTP qua LINE Notify thành công!")
        return True
    else:
        print(f"❌ Lỗi khi gửi LINE Notify: {response.text}")
        return False

# Flask app
app = Flask(__name__)

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/process_otp', methods=['POST'])
def process_otp():
    otp_codes = get_recent_unread_otp_emails()

    if otp_codes:
        otp_message = f"🔹 Đã xử lý {len(otp_codes)} mã OTP: {', '.join(otp_codes)}"
        send_line_notify(otp_message)
        return otp_message
    else:
        return "⚠ Không có email OTP mới trong 5 phút gần nhất."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
