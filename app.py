import os
import pickle
import base64
import requests
import re
import datetime
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

# Khai báo phạm vi quyền truy cập Gmail API
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def gmail_authenticate():
    """Xác thực OAuth2 từ biến môi trường trên Heroku."""
    creds = None

    # Lấy token OAuth2 từ biến môi trường
    if "TOKEN_PICKLE" in os.environ:
        token_data = base64.b64decode(os.environ["TOKEN_PICKLE"])
        creds = pickle.loads(token_data)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("oauth2_credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)

        # Mã hóa token và lưu vào biến môi trường Heroku (chỉ có tác dụng tạm thời)
        token_data = base64.b64encode(pickle.dumps(creds)).decode()
        os.environ["TOKEN_PICKLE"] = token_data  

    return build("gmail", "v1", credentials=creds)

def get_recent_unread_otp_emails():
    """Lấy các email OTP chưa đọc trong 5 phút gần nhất và đánh dấu đã đọc."""
    service = gmail_authenticate()
    otp_codes = []

    try:
        # Tính timestamp cho 5 phút trước (đổi về dạng Unix timestamp)
        five_minutes_ago = int((datetime.datetime.utcnow() - datetime.timedelta(minutes=5)).timestamp())

        # Chỉ lấy email chưa đọc trong 5 phút gần nhất
        query = f'after:{five_minutes_ago} subject:(Mã xác minh)'

        print(f"📌 Truy vấn Gmail với query: {query}")  # Debug query

        # Tìm các email phù hợp
        results = service.users().messages().list(userId="me", q=query, maxResults=5).execute()
        messages = results.get("messages", [])

        if messages:
            print(f"✅ Tìm thấy {len(messages)} email phù hợp!")

            for msg in messages:
                message = service.users().messages().get(userId="me", id=msg["id"]).execute()
                subject = ""

                for header in message["payload"]["headers"]:
                    if header["name"] == "Subject":
                        subject = header["value"]
                        break

                print(f"📩 Tiêu đề email: {subject}")  # Debug tiêu đề email

                # Tìm OTP trong tiêu đề email (6 chữ số)
                otp_match = re.search(r'\b\d{6}\b', subject)
                if otp_match:
                    otp_code = otp_match.group()
                    otp_codes.append(otp_code)
                    print(f"🔹 OTP tìm thấy: {otp_code}")  # Debug OTP

                # Đánh dấu email là đã đọc
                service.users().messages().modify(
                    userId="me",
                    id=msg["id"],
                    body={"removeLabelIds": ["UNREAD"]}
                ).execute()
                print("✅ Đã cập nhật trạng thái email thành 'Đã đọc'")

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
from flask import Flask, render_template, request

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
