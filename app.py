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

# Cấu hình logging (ghi log ra file)
logging.basicConfig(filename='otp_app.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Các phạm vi quyền truy cập
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Hàm xác thực
def gmail_authenticate(credentials_file, user_id):
    creds = None
    # Không cần file token_*.pickle trên Heroku nữa

    token_str = os.environ.get('GOOGLE_TOKEN')
    if token_str:
        try:
            creds = pickle.loads(token_str.encode('utf-8')) # Chuyển string thành bytes rồi load
        except Exception as e:
            logging.error(f"Lỗi load token từ biến môi trường: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Nếu không có token hợp lệ, vẫn cần xác thực (chỉ xảy ra 1 lần trên local)
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

            # *KHÔNG* lưu token vào file trên Heroku
            # Thay vào đó, cập nhật biến môi trường GOOGLE_TOKEN (CHỈ KHI CHẠY LOCAL)
            # Việc này chỉ cần thiết khi bạn CHẠY LẦN ĐẦU trên máy local để lấy token
            try: # Đảm bảo không lỗi khi không chạy local.
                import io
                token_bytes = io.BytesIO() # Dùng BytesIO thay vì file thật.
                pickle.dump(creds, token_bytes)
                os.environ['GOOGLE_TOKEN'] = token_bytes.getvalue().decode('utf-8') # Lưu vào biến môi trường (local)
                logging.info("Đã cập nhật biến môi trường GOOGLE_TOKEN (local).")

            except:
                pass



    service = build('gmail', 'v1', credentials=creds)
    return service

# Hàm lấy OTP
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
                        logging.warning(f"Gửi OTP {otp_code} thất bại.  Giữ email chưa đọc.")
        return otp_codes

    except requests.exceptions.RequestException as e:
        logging.error(f"Lỗi kết nối: {e}")
        return []
    except Exception as e:
        logging.error(f"Lỗi không xác định: {e}")
        return []

# Hàm gửi Line Notify (có retry)
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
        return -1  # Hoặc giá trị lỗi khác

def main(credentials_file, line_token, user_id):
    logging.info("Đang xác thực...")
    service = gmail_authenticate(credentials_file, user_id)

    logging.info("Đang kiểm tra email...")
    otp_codes = get_otp_emails(service, line_token)

    if otp_codes:
        logging.info(f"Đã xử lý {len(otp_codes)} mã OTP.")
    else:
        logging.info("Không có email OTP mới.")

def main_loop():
    # Lấy biến môi trường
    line_token = os.environ.get('LINE_NOTIFY_TOKEN')
    credentials_file = 'https://github.com/Kittyumbs/otp-line-notify/blob/main/client_secret_521752597957.json' # Đường dẫn đến file trong repo
    user_id = 'default'  #  Vì bạn chỉ dùng 1 tài khoản

    if not line_token:
        logging.error("Lỗi: Thiếu biến môi trường LINE_NOTIFY_TOKEN.")
        return  # Thoát nếu thiếu biến môi trường

    while True:
        try:
            main(credentials_file, line_token, user_id)
        except Exception as e:
            logging.error(f"Lỗi trong main loop: {e}")
        logging.info("Chờ 5 phút...")
        time.sleep(300)

if __name__ == "__main__":
    main_loop()
