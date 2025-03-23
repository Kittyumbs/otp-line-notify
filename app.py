import os
import pickle
import base64
import logging
import re
from flask import Flask, render_template, request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Khai báo phạm vi truy cập Gmail API
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

app = Flask(__name__)

# Gmail tập trung nhận OTP
CENTRALIZED_GMAIL = "me"

def gmail_authenticate():
    """Xác thực OAuth2 từ biến môi trường trên Heroku."""
    creds = None

    # Kiểm tra nếu có biến môi trường chứa token
    if "TOKEN_PICKLE" in os.environ:
        token_data = base64.b64decode(os.environ["TOKEN_PICKLE"])
        creds = pickle.loads(token_data)

    # Nếu token không tồn tại hoặc hết hạn, yêu cầu đăng nhập lại
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("oauth2_credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        
        # Mã hóa token và lưu vào biến môi trường Heroku
        token_data = base64.b64encode(pickle.dumps(creds)).decode()
        os.environ["TOKEN_PICKLE"] = token_data  # Tạm thời, cần cập nhật thủ công Heroku

    return build("gmail", "v1", credentials=creds)

def get_otp_emails():
    """Truy vấn Gmail API để lấy OTP từ email của tài khoản đăng nhập."""
    service = gmail_authenticate()
    otp_codes = []

    try:
        # Sửa userId thành "me" để chỉ lấy email của tài khoản đã xác thực OAuth2
        results = service.users().messages().list(userId="me", maxResults=5).execute()
        messages = results.get("messages", [])

        if messages:
            for msg in messages:
                message = service.users().messages().get(userId="me", id=msg["id"]).execute()
                subject = ""

                for header in message["payload"]["headers"]:
                    if header["name"] == "Subject":
                        subject = header["value"]
                        break

                # Tìm OTP trong tiêu đề email (6 chữ số)
                otp_match = re.search(r'\b\d{6}\b', subject)
                if otp_match:
                    otp_code = otp_match.group()
                    otp_codes.append(otp_code)

        return otp_codes

    except Exception as e:
        print(f"Lỗi khi lấy OTP từ Gmail: {e}")
        return []


@app.route('/')
def index():
    return render_template("index.html")

@app.route('/process_otp', methods=['POST'])
def process_otp():
    otp_codes = get_otp_emails()

    if otp_codes:
        return f"Đã xử lý {len(otp_codes)} mã OTP: {', '.join(otp_codes)}"
    else:
        return "Không có email OTP mới."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
