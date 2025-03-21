from flask import Flask, render_template
import os
import pickle
import requests
import re
import time
from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Tạo Flask app
app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

# Các phạm vi quyền truy cập
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Hàm xác thực với Gmail API
def gmail_authenticate(credentials_file):
    creds = None
    token_file = f'token_{os.path.basename(credentials_file)}.pickle'  # Chỉ lấy tên file JSON

    # Nếu đã có token, sử dụng lại
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)

    # Nếu chưa có token hoặc hết hạn, yêu cầu đăng nhập
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Lưu lại token vào file hợp lệ
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)

    return build('gmail', 'v1', credentials=creds)

# Hàm lấy các email mới có chứa OTP từ TikTok
def get_otp_emails(service, line_token):
    """ Lấy OTP từ email CHƯA ĐỌC trong vòng 5 phút gần nhất và gửi lên Line Notify """
    
    # Sử dụng datetime với timezone-aware để tránh lỗi
    now = datetime.now(timezone.utc)
    time_5_min_ago = int((now - timedelta(minutes=5)).timestamp())  # Chuyển thành timestamp UNIX

    # Gmail API query: Lọc email từ TikTok, chưa đọc và chỉ trong 5 phút gần nhất
    query = f"from:register@account.tiktok.com subject:(Mã xác minh) is:unread after:{time_5_min_ago}"
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])
    
    otp_codes = []

    for message in messages:
        # Lấy chi tiết email
        msg = service.users().messages().get(userId='me', id=message['id']).execute()
        
        # Lấy thời gian email gửi (dạng UNIX timestamp)
        email_timestamp = int(msg['internalDate']) // 1000  # Chuyển từ ms sang giây
        
        # Kiểm tra nếu email trong khoảng 5 phút gần nhất
        if email_timestamp >= time_5_min_ago:
            # Lọc tiêu đề email để lấy mã OTP
            subject = ''
            for header in msg['payload']['headers']:
                if header['name'] == 'Subject':
                    subject = header['value']  # Lấy tiêu đề email
            
            # Tìm mã OTP trong tiêu đề email (6 đến 8 chữ số)
            match = re.search(r'\d{6,8}', subject)
            
            if match:
                otp_code = match.group()  # Lấy mã OTP tìm thấy trong tiêu đề
                otp_codes.append(otp_code)  # Thêm vào danh sách OTP
                
                # Gửi OTP lên Line Notify
                send_status = send_line_notify(otp_code, line_token)

                # Nếu gửi thành công (status code 200), đánh dấu email là đã đọc
                if send_status == 200:
                    service.users().messages().modify(
                        userId='me', id=message['id'], body={'removeLabelIds': ['UNREAD']}
                    ).execute()
                    print(f"✅ Đã gửi OTP {otp_code} lên Line Notify và đánh dấu email là đã đọc.")
                else:
                    print(f"❌ Gửi OTP {otp_code} lên Line Notify thất bại! Email vẫn chưa đọc để thử lại sau.")

    return otp_codes

# Gửi thông báo qua Line Notify
def send_line_notify(message, token):
    url = 'https://notify-api.line.me/api/notify'
    headers = {
        'Authorization': 'Bearer ' + token
    }
    payload = {'message': message}
    r = requests.post(url, headers=headers, data=payload)
    return r.status_code

def main(credentials_file, line_token):
    """ Hàm chính để chạy toàn bộ chương trình """
    print("🔄 Đang xác thực với Gmail API...")
    service = gmail_authenticate(credentials_file)  # Xác thực Gmail API

    print("📩 Đang kiểm tra email mới...")
    otp_codes = get_otp_emails(service, line_token)  # Lấy OTP từ Gmail và gửi lên Line Notify

    if otp_codes:
        print(f"✅ Đã xử lý xong {len(otp_codes)} mã OTP!")
    else:
        print("❌ Không có email OTP nào trong 5 phút gần nhất.")

    print("🚀 Chương trình hoàn tất!")

# Example call to the main function (when running the script)
# Bạn cần thay đổi `YOUR_LINE_NOTIFY_TOKEN` thành token thật mà bạn có từ Line Notify
line_token = '0IxJmPEsNKZr42aAYBJIXOS8MKkCZy97GrbG9XM5esl'
credentials_file = 'C:/Users/Kittyumbs/Downloads/TEST_OTP/client_secret_521752597957.json'  # Chỉnh lại đuôi `.json`
main(credentials_file, line_token)
