# app.py
import os
import re
import json
import time
import base64
import pickle
import requests
from datetime import datetime
from pytz import timezone
from markupsafe import Markup
from flask import Flask, render_template, request, url_for
from flask_cors import CORS
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
app = Flask(__name__)
CORS(app)
HISTORY_FILE = "/tmp/otp_history.json"

def gmail_authenticate():
    token_env = os.environ.get("TOKEN_PICKLE")
    if not token_env:
        print("❌ Không tìm thấy biến môi trường TOKEN_PICKLE!")
        return None
    try:
        creds = pickle.loads(base64.b64decode(token_env))
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            new_token = base64.b64encode(pickle.dumps(creds)).decode()
            update_heroku_token(new_token)
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        print(f"❌ Lỗi auth: {e}")
        return None

def update_heroku_token(new_token):
    api_key = os.getenv("HEROKU_API_KEY")
    app_name = os.getenv("HEROKU_APP_NAME")
    if not api_key or not app_name:
        return False
    url = f"https://api.heroku.com/apps/{app_name}/config-vars"
    headers = {
        "Accept": "application/vnd.heroku+json; version=3",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    resp = requests.patch(url, headers=headers, json={"TOKEN_PICKLE": new_token})
    return resp.status_code == 200

def get_recent_unread_otp_emails():
    service = gmail_authenticate()
    if not service:
        return []
    five_min = int(time.time()) - 300
    q = f"from:register@account.tiktok.com is:unread after:{five_min}"
    try:
        res = service.users().messages().list(userId="me", q=q, maxResults=5).execute()
        msgs = res.get("messages", [])
        otps = []
        for m in msgs:
            msg = service.users().messages().get(userId="me", id=m["id"]).execute()
            subj = next(h["value"] for h in msg["payload"]["headers"] if h["name"]=="Subject")
            mch = re.search(r"\b\d{6}\b", subj)
            if mch: otps.append(mch.group())
            service.users().messages().modify(
                userId="me", id=m["id"], body={"removeLabelIds": ["UNREAD"]}
            ).execute()
        return otps
    except:
        return []

def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE) as f:
                data = json.load(f)
                today = datetime.now().strftime("%Y-%m-%d")
                if data and data[0]["time"].startswith(today):
                    return data
    except:
        pass
    return []

def save_history(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/history")
def get_history():
    return json.dumps(load_history())

@app.route("/process_otp", methods=["POST"])
def process_otp():
    vn_time = datetime.now(timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
    history = load_history()
    try:
        otps = get_recent_unread_otp_emails()
        if otps:
            msg = (
                f"<i class='fas fa-check-circle' style='color:green'></i> "
                f"Đã xử lý {len(otps)} OTP: {', '.join(otps)}"
            )
        else:
            msg = "<i class='fas fa-exclamation-circle' style='color:orange'></i> Không có OTP mới."
    except Exception as e:
        msg = f"<i class='fas fa-times-circle' style='color:red'></i> Lỗi: {e}"
    history.append({"time": vn_time, "result": msg})
    save_history(history)
    return Markup(msg)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
