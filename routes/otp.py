import os,random,base64,httpx
from email.mime.text import MIMEText
from datetime import datetime,timedelta
from dotenv import load_dotenv
load_dotenv()
from database import auth_db

OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES", "10"))
otp_col = auth_db.otps

SMTP_EMAIL = os.getenv("SMTP_EMAIL")  
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

async def get_access_token_from_refresh(refresh_token: str) -> str:
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
        return data.get("access_token")


async def send_gmail_email(access_token: str, to_email: str, subject: str, body: str):
    message = MIMEText(body, "html")
    message["to"] = to_email
    message["from"] = SMTP_EMAIL
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
        if resp.status_code != 200:
            raise Exception(f"Failed to send email: {resp.text}")
        return resp.json()

def generate_otp() -> str:
    """6-digit OTP as string"""
    return str(random.randint(100000, 999999)).zfill(6)

async def send_otp_email_async(to_email: str, otp: str) -> bool:
    """Send OTP email via Gmail API."""
    html_body = f"""
    <html>
      <body style="font-family: 'Segoe UI', Roboto, Arial, sans-serif; background: linear-gradient(135deg, #1F2A6E 0%, #283593 100%); margin: 0; padding: 40px 0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 14px; box-shadow: 0 4px 16px rgba(0,0,0,0.15); overflow: hidden;">
          
          <!-- Header -->
          <tr>
            <td style="background-color: #1F2A6E; padding: 35px 20px; text-align: center;">
              <h1 style="color: #ffffff; font-size: 26px; margin: 0;">AegisSecure</h1>
              <p style="color: #dbe4ff; margin: 6px 0 0; font-size: 14px;">Protecting you from online threats.</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding: 36px 40px;">
              <h2 style="color: #111827; font-size: 20px; margin-bottom: 14px; text-align: center;">Verification</h2>
              <p style="color: #4b5563; font-size: 15px; line-height: 1.6; text-align: center;">
                Please use the following one-time passcode (OTP) for the verification process.
              </p>

              <div style="margin: 30px 0; text-align: center;">
                <div style="
                  display: inline-block;
                  background: #1F2A6E;
                  color: #ffffff;
                  padding: 16px 32px;
                  font-size: 30px;
                  font-weight: 600;
                  letter-spacing: 8px;
                  border-radius: 10px;
                  box-shadow: 0 4px 8px rgba(31,42,110,0.35);
                ">
                  {otp}
                </div>
              </div>

              <p style="color: #4b5563; font-size: 15px; line-height: 1.6; text-align: center;">
                This code will be valid for 
                <span style="color: #1F2A6E; font-weight: 600;">{OTP_EXPIRE_MINUTES} minutes</span>.
                Please complete your verification within this time.
              </p>

              <p style="color: #9ca3af; font-size: 13px; margin-top: 24px; text-align: center;">
                If you didn’t request this verification, you can safely ignore this message.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #f9fafb; padding: 18px 30px; text-align: center; border-top: 1px solid #e5e7eb;">
              <p style="color: #9ca3af; font-size: 13px; margin: 0;">
                © {datetime.now().year} AegisSecure — All rights reserved<br>
                <span style="color: #6b7280;">Stay protected. Stay informed.</span>
              </p>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    try:
        access_token = await get_access_token_from_refresh(REFRESH_TOKEN)
        if not access_token:
            print("[DEBUG] Failed to get access token")
            return False
        await send_gmail_email(access_token, to_email, "AegisSecure OTP", html_body)
        print(f"[DEBUG] OTP sent via Gmail API to {to_email}")
        return True
    except Exception as e:
        print("Failed to send OTP via Gmail API:", e)
        # print(f"[DEV OTP] {to_email} -> {otp}")
        return False


async def store_otp(email: str, otp: str):
    await otp_col.delete_many({"email": email})
    doc = {
        "email": email,
        "otp": otp,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=OTP_EXPIRE_MINUTES),
        "verified": False,
    }
    await otp_col.insert_one(doc)


async def verify_otp_in_db(email: str, otp: str) -> bool:
    email = email.lower()
    otp = str(otp).zfill(6)
    doc = await otp_col.find_one({
        "email": email,
        "otp": otp,
        "verified": False,
        "expires_at": {"$gt": datetime.utcnow()}
    })
    if doc:
        await otp_col.update_one({"_id": doc["_id"]}, {"$set": {"verified": True}})
        return True
    return False


async def ensure_otp_indexes():
    await otp_col.create_index("email")
    await otp_col.create_index("expires_at", expireAfterSeconds=0)