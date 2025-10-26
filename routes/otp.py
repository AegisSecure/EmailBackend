import os
import asyncio
import random
import datetime
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
load_dotenv()

from database import auth_db, accounts_col  # accounts_col stores Gmail refresh tokens

import httpx

# -------------------
# Config & DB
# -------------------
OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES", "10"))
otp_col = auth_db.otps

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# -------------------
# Gmail API helper
# -------------------
async def get_access_token_from_refresh(refresh_token: str) -> str:
    """Get new access token from refresh token."""
    print(f"[DEBUG] Getting access token using refresh_token: {refresh_token[:10]}...")  # only first 10 chars
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }
        )
        data = resp.json()
        print(f"[DEBUG] Access token response: {data}")
        return data.get("access_token")

async def send_gmail_email(access_token: str, from_email: str, to_email: str, subject: str, body: str):
    """Send an email via Gmail API."""
    print(f"[DEBUG] Sending email from {from_email} -> {to_email} via Gmail API")
    message = MIMEText(body, "html")
    message["to"] = to_email
    message["from"] = from_email
    message["subject"] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={"raw": raw_message}
        )
        print(f"[DEBUG] Gmail API send response: {resp.status_code}, {resp.text}")
        if resp.status_code != 200:
            raise Exception(f"Failed to send email: {resp.text}")
        return resp.json()

# -------------------
# OTP helpers
# -------------------
def generate_otp() -> str:
    """6-digit OTP as string"""
    otp = str(random.randint(100000, 999999)).zfill(6)
    print(f"[DEBUG] Generated OTP: {otp}")
    return otp

async def send_otp_email_async(to_email: str, otp: str) -> bool:
    """Send OTP via Gmail API → SMTP fallback → dev print"""
    print(f"[DEBUG] Preparing to send OTP to {to_email}")

    html_body = f"""
    <html>
      <body style='font-family: Arial, sans-serif;'>
        <h2>AegisSecure — Verification Code</h2>
        <p>Your verification code is:</p>
        <h1 style='letter-spacing:6px'>{otp}</h1>
        <p>This code will expire in {OTP_EXPIRE_MINUTES} minutes.</p>
      </body>
    </html>
    """

    # --- Gmail API ---
    user_data = await accounts_col.find_one({"gmail_email": os.getenv("SMTP_EMAIL")})
    refresh_token = user_data.get("refresh_token") if user_data else None

    if refresh_token:
        try:
            access_token = await get_access_token_from_refresh(refresh_token)
            if access_token:
                await send_gmail_email(access_token, os.getenv("SMTP_EMAIL"), to_email, "AegisSecure OTP", html_body)
                print(f"[DEBUG] OTP sent via Gmail API to {to_email}")
                return True
            else:
                print("[DEBUG] Failed to get access token")
        except Exception as e:
            print("❌ Failed to send OTP via Gmail API:", e)

    # --- SMTP fallback ---
    if os.getenv("SMTP_EMAIL") and os.getenv("SMTP_PASSWORD"):
        def _sync_send_email():
            msg = MIMEMultipart()
            msg["From"] = os.getenv("SMTP_EMAIL")
            msg["To"] = to_email
            msg["Subject"] = "AegisSecure OTP"
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(os.getenv("SMTP_SERVER", "smtp.gmail.com"),
                              int(os.getenv("SMTP_PORT", 587))) as server:
                server.starttls()
                server.login(os.getenv("SMTP_EMAIL"), os.getenv("SMTP_PASSWORD"))
                server.send_message(msg)

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _sync_send_email)
            print(f"[DEBUG] OTP sent via SMTP to {to_email}")
            return True
        except Exception as e:
            print("❌ Failed to send OTP via SMTP:", e)

    # --- Final fallback ---
    print(f"[DEV OTP] {to_email} -> {otp}")
    return False

async def store_otp(email: str, otp: str):
    """Store OTP in DB and remove previous ones"""
    print(f"[DEBUG] Storing OTP for {email}")
    await otp_col.delete_many({"email": email})
    doc = {
        "email": email,
        "otp": otp,
        "created_at": datetime.datetime.utcnow(),
        "expires_at": datetime.datetime.utcnow() + datetime.timedelta(minutes=OTP_EXPIRE_MINUTES),
        "verified": False,
    }
    await otp_col.insert_one(doc)
    print(f"[DEBUG] OTP stored: {doc}")

async def verify_otp_in_db(email: str, otp: str) -> bool:
    email = email.lower()
    otp = str(otp).zfill(6)
    print(f"[DEBUG] Verifying OTP {otp} for {email}")
    doc = await otp_col.find_one({
        "email": email,
        "otp": otp,
        "verified": False,
        "expires_at": {"$gt": datetime.datetime.utcnow()}
    })
    print(f"[DEBUG] OTP lookup result: {doc}")
    if doc:
        await otp_col.update_one({"_id": doc["_id"]}, {"$set": {"verified": True}})
        print(f"[DEBUG] OTP verified and marked as used")
        return True
    return False

async def ensure_otp_indexes():
    """Create indexes for OTP collection"""
    try:
        await otp_col.create_index("email")
        await otp_col.create_index("expires_at", expireAfterSeconds=0)
        print("[DEBUG] OTP indexes ensured")
    except Exception as e:
        print("ensure_otp_indexes error:", e)
