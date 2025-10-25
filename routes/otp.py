# routes/otp.py
import os
import asyncio
import random
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
load_dotenv()

from database import auth_db  # uses your database.py which exports auth_db

# config (use env vars)
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_EMAIL = os.getenv("SMTP_EMAIL")        # set this in .env for real email
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")  # set app password in .env
OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES", "10"))

# OTP collection
otp_col = auth_db.otps

def generate_otp() -> str:
    """6-digit OTP as string"""
    return str(random.randint(100000, 999999)).zfill(6)

def _sync_send_email(to_email: str, subject: str, html_body: str) -> None:
    """Blocking SMTP send; run in executor from async code."""
    msg = MIMEMultipart()
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)

async def send_otp_email_async(to_email: str, otp: str) -> bool:
    
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        # dev fallback: print OTP for testing
        print(f"[DEV OTP] {to_email} -> {otp}")
        return False

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
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _sync_send_email, to_email, "AegisSecure OTP", html_body)
        return True
    except Exception as e:
        print("❌ Failed to send OTP email:", e)
        return False

async def store_otp(email: str, otp: str):
    """Store OTP document and remove previous OTPs for the email."""
    await otp_col.delete_many({"email": email})
    doc = {
        "email": email,
        "otp": otp,
        "created_at": datetime.datetime.utcnow(),
        "expires_at": datetime.datetime.utcnow() + datetime.timedelta(minutes=OTP_EXPIRE_MINUTES),
        "verified": False,
    }
    await otp_col.insert_one(doc)

async def verify_otp_in_db(email: str, otp: str) -> bool:
    email = email.lower()
    otp = str(otp).zfill(6)
    print(f"🔍 Checking OTP for email={email}, otp={otp}")

    doc = await otp_col.find_one({
        "email": email,
        "otp": otp,
        "verified": False,
        "expires_at": {"$gt": datetime.datetime.utcnow()}
    })
    print(f"🗂 Found doc: {doc}")

    if doc:
        await otp_col.update_one({"_id": doc["_id"]}, {"$set": {"verified": True}})
        return True

    return False


async def ensure_otp_indexes():
    """Create indexes for OTP collection (email index + TTL on expires_at)."""
    try:
        await otp_col.create_index("email")
        await otp_col.create_index("expires_at", expireAfterSeconds=0)
    except Exception as e:
        print("ensure_otp_indexes error:", e)