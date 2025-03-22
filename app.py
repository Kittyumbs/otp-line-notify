import os
import pickle
import requests
import re
import time
from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from tenacity import retry, stop_after_attempt, wait_fixed
import logging
import json  # Import thư viện json
from flask import Flask, render_template, request

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Các phạm vi quyền truy cập
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
app = Flask(__name__)

def gmail_authenticate(user_id):
    creds = None

    token_str = os.environ.get('GOOGLE_TOKEN')
    if token_str:
        try:
            creds = pickle.loads(token_str.encode('utf-8'))
        except Exception as e:
            logging.error(f"Lỗi giải mã token: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
           # Xác thực (chỉ trên local)
            try:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES) # Dùng file credentials.json
                creds = flow.run_local_server(port=0)
                import io
                token_bytes = io.BytesIO()
                pickle.dump(creds, token_bytes)
                os.environ['GOOGLE_TOKEN'] = token_bytes.getvalue().decode('utf-8') # Cập nhật biến môi trường GOOGLE_TOKEN
                logging.info("Đã cập nhật GOOGLE_TOKEN (local)")
            except Exception as e:
                logging.error(f"Error during local authentication: {e}") # Ghi log lỗi
                pass

    service = build('gmail', 'v1', credentials=creds)
    return service
#... (các hàm khác giữ nguyên) ...
def get_otp_emails(service, line_token):
    try:
        now = datetime.now(timezone.utc)
        time_5_min_ago = int((now - timedelta(minutes=5)).timestamp())

        query = f"from:register@account.tiktok.com subject:(Mã xác minh) is:unread after:{time_5_min_ago}"
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])

        otp_codes = []
        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            email_timestamp = int(msg['internalDate']) // 1000

            if email_timestamp >= time_5_min_ago:
                subject = ''
                for header in msg['payload']['headers']:
                    if header['name'] == 'Subject':
                        subject = header['value']

                match = re.search(r'\d{6,8}', subject)
                if match:
                    otp_code = match.group()
                    otp_codes.append(otp_code)
                    send_status = send_line_notify_with_retry(otp_code, line_token)

                    if send_status == 200:
                        service.users().messages().modify(
                            userId='me', id=message['id'], body={'removeLabelIds': ['UNREAD']}
                        ).execute()
                        logging.info(f"Đã gửi OTP {otp_code} và đánh dấu email là đã đọc.")
                    else:
                        logging.warning(f"Gửi OTP {otp_code} thất bại. Giữ email chưa đọc.")
        return otp_codes

    except requests.exceptions.RequestException as e:
        logging.error(f"Lỗi kết nối: {e}")
        return []
    except Exception as e:
        logging.error(f"Lỗi không xác định: {e}")
        return []

# Hàm gửi Line Notify (có retry) (giữ nguyên)
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def send_line_notify_with_retry(message, token):
    url = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': 'Bearer ' + token}
    payload = {'message': message}
    try:
        r = requests.post(url, headers=headers, data=payload)
        return r.status_code
    except requests.exceptions.RequestException as e:
        logging.error(f"Lỗi khi gửi Line Notify: {e}")
        return -1

# --- Route cho trang chủ (index.html) ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Route để xử lý khi người dùng nhấn nút (nếu cần) ---
@app.route('/process_otp', methods=['POST']) # Đổi tên route và method cho phù hợp
def process_otp():
    line_token = os.environ.get('LINE_NOTIFY_TOKEN')
    user_id = 'default'

    if not line_token:
        return "Lỗi: Thiếu biến môi trường LINE_NOTIFY_TOKEN."

    service = gmail_authenticate(user_id)
    otp_codes = get_otp_emails(service, line_token)

    if otp_codes:
        return f"Đã xử lý {len(otp_codes)} mã OTP."
    else:
        return "Không có email OTP mới."

if __name__ == "__main__":
  #Tạo file credentials.json TẠM THỜI
    try:
      creds_info = json.loads(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))
      with open("credentials.json", "w") as f:
        json.dump(creds_info, f)
    except:
      pass
    app.run(debug=False) # Bỏ debug=True
