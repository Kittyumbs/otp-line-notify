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

# Cấu hình logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Các phạm vi quyền truy cập
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Hàm xác thực
def gmail_authenticate(user_id):
    creds = None

    # Thay thế dòng này:
    # token_str = os.environ.get('GOOGLE_TOKEN')
    # Bằng dòng này (dán trực tiếp token vào):
    token_str = "ya29.a0AeXRPp65Abdn9nS-_LGii1Dyn36pEbd6fl4PuQZdeTborp0x6Aat-Q7v7oySVY1IpbtFvdGi0GWCOOG8zrkVq89NR_6xKRxonG54Vc084qSTZu8nwTQWEXjNd4I9trCEV-5u_DlrOOtHLJVe7sJBgSuBAFt6KaSV8KTPVSwraCgYKAXoSARASFQHGX2Mi8QIs7B4BWsvQjpNgx0T2CQ0175"

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
          # Chạy xác thực (nếu token không hợp lệ/hết hạn - cần trên local)
          try:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES) # Tên file credentials.json tạm
            creds = flow.run_local_server(port=0)

            # Sau khi xác thực THÀNH CÔNG, in ra token để bạn copy và DÁN LẠI VÀO CODE
            import io
            token_bytes = io.BytesIO()
            pickle.dump(creds, token_bytes)
            print("=" * 20)
            print("SAO CHÉP CHUỖI SAU VÀ DÁN VÀO CODE (thay thế cho token hiện tại):")
            print(token_bytes.getvalue().decode('utf-8'))
            print("=" * 20)
          except:
             pass

    service = build('gmail', 'v1', credentials=creds)
    return service

# ... (Phần còn lại của code giữ nguyên) ...
# (Phần gửi Line, hàm main, v.v.)

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
    # Lấy biến môi trường từ Heroku
    line_token = os.environ.get('LINE_NOTIFY_TOKEN')
    user_id = 'default'  # Bạn có thể thay đổi nếu cần
     # Tạo file credentials.json tạm (nếu cần)
    try:
        import json
        creds_info = json.loads(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))
        with open("credentials.json", "w") as f:
          json.dump(creds_info, f)

    except:
        pass
    if not line_token:
        logging.error("Lỗi: Thiếu biến môi trường LINE_NOTIFY_TOKEN.")
    else:
      main(line_token,user_id) # Chạy hàm main
