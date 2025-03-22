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
import json  # Thêm thư viện json

# Cấu hình logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Các phạm vi quyền truy cập
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Hàm xác thực (sử dụng token cố định và biến môi trường)
def gmail_authenticate(user_id):
    creds = None

    # ✅ SỬ DỤNG TOKEN CỐ ĐỊNH (KHÔNG KHUYẾN KHÍCH)
    token_str = "ya29.a0AeXRPp65Abdn9nS-_LGii1Dyn36pEbd6fl4PuQZdeTborp0x6Aat-Q7v7oySVY1IpbtFvdGi0GWCOOG8zrkVq89NR_6xKRxonG54Vc084qSTZu8nwTQWEXjNd4I9trCEV-5u_DlrOOtHLJVe7sJBgSuBAFt6KaSV8KTPVSwraCgYKAXoSARASFQHGX2Mi8QIs7B4BWsvQjpNgx0T2CQ0175"

    if token_str:
        try:
            creds = pickle.loads(token_str.encode('utf-8'))
        except Exception as e:
            logging.error(f"Lỗi giải mã token: {e}")
            creds = None

    # KHÔNG CÓ PHẦN XÁC THỰC TƯƠNG TÁC Ở ĐÂY (vì bạn dùng token cố định)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())


    service = build('gmail', 'v1', credentials=creds)
    return service

# (Các hàm get_otp_emails, send_line_notify_with_retry giữ nguyên)
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

def main(line_token, user_id):
    logging.info("Đang xác thực...")
    service = gmail_authenticate(user_id)

    logging.info("Đang kiểm tra email...")
    otp_codes = get_otp_emails(service, line_token)

    if otp_codes:
        logging.info(f"Đã xử lý {len(otp_codes)} mã OTP.")
    else:
        logging.info("Không có email OTP mới.")
    logging.info("Chương trình kết thúc.")

if __name__ == "__main__":
    # Lấy biến môi trường từ Heroku/local
    line_token = os.environ.get('LINE_NOTIFY_TOKEN')
    user_id = 'default'

    # Tạo file credentials.json TẠM THỜI từ biến môi trường
    try:
        creds_info = json.loads(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))
        with open("credentials.json", "w") as f: # Ghi vào file tạm
            json.dump(creds_info, f)
    except:
        pass  # Nếu không có biến môi trường, bỏ qua

    if not line_token:
        logging.error("Lỗi: Thiếu biến môi trường LINE_NOTIFY_TOKEN.")
    else:
        main(line_token, user_id)
