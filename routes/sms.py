from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from datetime import datetime
from dotenv import load_dotenv
from .auth import get_current_user
from database import sms_messages_col
from websocket_manager import broadcast_new_email
import hashlib
import httpx
import os
from fastapi.encoders import jsonable_encoder
from routes.notifications import get_spam_prediction


router = APIRouter()
load_dotenv()

CYBER_MODEL_URL = os.getenv("CYBER_SECURE_API_URI")
class SmsMessage(BaseModel):
    address: str
    body: str
    date_ms: int
    type: str

class SmsSyncRequest(BaseModel):
    messages: List[SmsMessage]

def generate_message_hash(address: str, body: str, date_ms: int):
    text = f"{address}-{body}-{date_ms}"
    return hashlib.sha256(text.encode()).hexdigest()


def serialize_doc(doc):
    doc["_id"] = str(doc["_id"])
    if isinstance(doc.get("created_at"), datetime):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc

@router.post("/sync")
async def sync_sms(request: SmsSyncRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    inserted_count = 0
    for msg in request.messages:
        msg_hash = generate_message_hash(msg.address, msg.body, msg.date_ms)

        existing = await sms_messages_col.find_one({"hash": msg_hash, "user_id": user_id})
        if existing:
            continue
        combined_text=f"{""}{""}{msg.body}"
        spam_analysis = await get_spam_prediction(combined_text)

        message_doc = {
            "user_id": user_id,
            "address": msg.address,
            "body": msg.body,
            "timestamp": msg.date_ms,
            "type": msg.type,
            "hash": msg_hash,
            "spam_score": spam_analysis.get("confidence"),
            "created_at": datetime.utcnow(),
            "spam_reasoning": spam_analysis.get("reasoning"),
            "spam_highlighted_text": spam_analysis.get("highlighted_text"),
            "spam_suggestion": spam_analysis.get("suggestion"),
            "spam_verdict": spam_analysis.get("final_decision"),
        }

        await sms_messages_col.insert_one(message_doc)
        inserted_count += 1
        await broadcast_new_email(message_doc)

    return {
        "status": "success",
        "inserted": inserted_count,
        "user_id": user_id,
    }

@router.get("/all")
async def get_all_sms(current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    messages = await sms_messages_col.find({"user_id": user_id}).sort("timestamp", -1).to_list(100)
    serialized_messages = [serialize_doc(m) for m in messages]

    return {"sms_messages": jsonable_encoder(serialized_messages)}
