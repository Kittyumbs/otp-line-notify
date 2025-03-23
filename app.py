import os
import base64
import json
import requests
import re
import time
from datetime import datetime, timedelta, timezone
from google.oauth2 import service_account  # Dùng service_account
from googleapiclient.discovery import build
from tenacity import retry, stop_after_attempt, wait_fixed
import logging
from flask import Flask, render_template, request
from dotenv import load_dotenv

load_dotenv()  # Tải biến môi trường từ .env (nếu có)

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Các phạm vi quyền truy cập
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
app = Flask(__name__)

def get_service_account_credentials():
    """
    Lấy chuỗi Base64 từ biến môi trường và giải mã nó thành thông tin đăng nhập của Service Account.
    """
    base64_string = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')

    if base64_string:
        # Giải mã chuỗi Base64 thành dữ liệu JSON
        json_data = base64.b64decode(base64_string).decode('utf-8')
        creds_info = json.loads(json_data)
        
        # Sử dụng service account credentials
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        return creds
    else:
        logging.error("Không tìm thấy biến môi trường GOOGLE_APPLICATION_CREDENTIALS.")
        return None

def gmail_authenticate(user_id):
    """
    Xác thực ứng dụng với Gmail API bằng Service Account Credentials.
    """
    creds = get_service_account_credentials()
    if not creds:
        logging.error("Không thể lấy thông tin xác thực từ Service Account.")
        return None

    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        logging.error(f"Error building Gmail service: {e}")
        return None

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
                        break

                match = re.search(r'\d{6,8}', subject)
                if match:
                    otp_code = match.group()
                    otp_codes.append(otp_code)
                    send_status = send_line_notify_with_retry(otp_code, line_token)

                    if send_status == 200:
                        service.users().messages().modify(
                            userId='me', id=message['id'], body={'removeLabelIds': ['UNREAD']}).execute()
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_otp', methods=['POST'])
def process_otp():
    line_token = os.environ.get('LINE_NOTIFY_TOKEN')
    user_id = 'default'  # Bạn có thể không cần dùng user_id

    if not line_token:
        return "Lỗi: Thiếu biến môi trường LINE_NOTIFY_TOKEN."

    service = gmail_authenticate(user_id)
    if service is None:
        return "Lỗi: Không thể xác thực với Gmail."

    otp_codes = get_otp_emails(service, line_token)

    if otp_codes:
        return f"Đã xử lý {len(otp_codes)} mã OTP."
    else:
        return "Không có email OTP mới."

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
