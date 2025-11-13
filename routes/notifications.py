from fastapi import APIRouter, Request
import httpx
from database import messages_col, accounts_col
import os, json, base64
from dotenv import load_dotenv
from websocket_manager import broadcast_new_email
from datetime import datetime, timezone
from pydantic import BaseModel
load_dotenv()
router = APIRouter()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
CYBER_SECURE_URI=os.getenv("CYBER_SECURE_API_URI")
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    raise Exception("Google OAuth credentials are missing in .env")

class Spam_request(BaseModel):
    sender: str
    subject: str
    body: str
    
async def get_spam_prediction(req:Spam_request):
    try:
        async with httpx.AsyncClient() as client:
            sender=req.sender
            subject=req.subject
            body=req.body
            resp = await client.post(
                CYBER_SECURE_URI,
                json={
                    "sender": sender,
                    "subject": subject,
                    "body": body
                },
                timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data
            return {"confidence": data, "reasoning": None}

    except Exception as e:
        print("### Spam prediction failed:", repr(e))
        return {
            "confidence": "unknown",
            "reasoning": None,
            "highlighted_text": None,
            "suggestion": None,
            "final_decision": "unknown"
        }

async def get_access_token_from_refresh(refresh_token: str):
    """Get a new Google access token using the refresh token."""
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



@router.post("/analyze_text")
async def analyze_text_endpoint(data: dict):
    text = data.get("text", "")
    if not text:
        return {"prediction": "UNKNOWN"} 

    try:
        
        prediction = await get_spam_prediction(text)
        prediction_str = str(prediction).strip().upper() 
        if prediction_str not in ["SPAM", "HAM"]:
            prediction_str = "UNKNOWN"
        return {"prediction": prediction_str}
    except Exception as e:
        print("Error in analyze_text_endpoint:", e)
        return {"prediction": "UNKNOWN"}
    

def extract_body(payload):
    """Recursively extract text/plain body from Gmail message payload."""
    if not payload:
        return None

    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if body_data and ("text/plain" in mime_type or "text/html" in mime_type):
        try:
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
        except Exception:
            return None

    for part in payload.get("parts", []):
        text = extract_body(part)
        if text:
            return text

    return None


@router.post("/gmail/notifications")
async def gmail_notifications(request: Request):
    try:
        raw_data = await request.json()
        if "message" not in raw_data:
            return {"status": "ignored"}

        
        msg_str = base64.b64decode(raw_data["message"]["data"]).decode("utf-8")
        msg = json.loads(msg_str)

        email_address = msg.get("emailAddress")
        history_id = msg.get("historyId")
        print(f"Gmail Push Notification for {email_address} | historyId={history_id}")

        if not email_address:
            return {"status": "error", "message": "Missing emailAddress in notification"}

        
        user = await accounts_col.find_one({"gmail_email": email_address})
        if not user or "refresh_token" not in user:
            print(f"Missing refresh_token for {email_address}")
            return {"status": "ignored"}
        access_token = await get_access_token_from_refresh(user["refresh_token"])
        if not access_token:
            print(f"Failed to get access_token for {email_address}")
            return {"status": "error"}

        async with httpx.AsyncClient() as client:
            start_history_id = user.get("last_history_id", history_id)
            history_resp = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/history",
                params={"startHistoryId": start_history_id},
                headers={"Authorization": f"Bearer {access_token}"}
            )
            history_data = history_resp.json()

            for record in history_data.get("history", []):
                for msg_event in record.get("messages", []):
                    msg_id = msg_event["id"]
                    msg_resp = await client.get(
                        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=full",
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    msg_data = msg_resp.json()
                    headers = msg_data.get("payload", {}).get("headers", [])
                    subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
                    sender = next((h["value"] for h in headers if h["name"] == "From"), "")
                    snippet = msg_data.get("snippet", "")
                    body = extract_body(msg_data.get("payload", {})) or snippet
                    combined_text = f"{sender}{subject} {body}"
                    spam_prediction = await get_spam_prediction(combined_text)
                    await messages_col.update_one(
                        {"user_id": user["user_id"], "gmail_email": email_address, "gmail_id": msg_id},
                        {"$set": {
                            "subject": subject,
                            "from": sender,
                            "snippet": snippet,
                            "body": body,
                            "timestamp": int(msg_data.get("internalDate", datetime.now(timezone.utc).timestamp() * 1000)),
                            "spam_prediction": spam_prediction.get("confidence"),
                            "spam_reasoning": spam_prediction.get("reasoning"),
                            "spam_highlighted_text": spam_prediction.get("highlighted_text"),
                            "spam_suggestion": spam_prediction.get("suggestion"),
                            "spam_verdict": spam_prediction.get("final_decision"),
                        }},
                        upsert=True
                    )
        # print(f"Stored email: {subject[:40]} | body length={len(body)} | sender={sender}")
        await accounts_col.update_one(
            {"gmail_email": email_address},
            {"$set": {"last_history_id": history_id}}
        )
        await broadcast_new_email(email_address)

        return {"status": "processed"}

    except Exception as e:
        import traceback
        print("Error in gmail_notifications:", str(e))
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
