from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from database import messages_col, accounts_col
import time,os
router = APIRouter()
JWT_SECRET = os.getenv("JWT_SECRET", "your_secret_key")
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

@router.get("/gmail/state-token")
def get_state_token(user_id: str):
    payload = {
        "user_id": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300  # expires in 5 minutes
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return {"state": token}

async def get_current_user_id(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing user_id")
        return user_id
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
@router.get("/emails")
async def get_emails(
    user_id: str = Depends(get_current_user_id),
    account: str | None = None,
):
    """
    Fetch emails for the authenticated user.
    If `account` query param is provided, only return emails for that Gmail account.
    """
    try:
        query = {"user_id": user_id}
        if account:
            query["gmail_email"] = account  # filter by selected Gmail account

        emails_cursor = messages_col.find(query, {"_id": 0})
        emails = await emails_cursor.to_list(length=None)

        # Normalize timestamps
        for e in emails:
            if "timestamp" in e:
                e["timestamp"] = int(e["timestamp"])
            elif "date" in e:
                e["timestamp"] = int(e.pop("date", 0))
            else:
                e["timestamp"] = 0

        # Sort newest first
        emails_sorted = sorted(emails, key=lambda e: e.get("timestamp", 0), reverse=True)
        return emails_sorted

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.get("/user/me")
async def get_current_user(user_id: str):
    user = await accounts_col.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"name": user.get("name", "User"), "gmail_email": user.get("gmail_email")}



# --------------⭐️
@router.get("/gmail/accounts")
async def get_connected_accounts(user_id: str = Depends(get_current_user_id)):
    """
    Return all Gmail accounts connected by this user.
    """
    try:
        accounts_cursor = accounts_col.find(
            {"user_id": user_id},
            {"_id": 0, "gmail_email": 1, "connected_at": 1}
        )
        accounts = await accounts_cursor.to_list(length=None)
        return {"accounts": accounts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
@router.post("/accounts/delete")
async def delete_connected_account(
    payload: dict,
    user_id: str = Depends(get_current_user_id)
):
    gmail_email = payload.get("gmail_email")
    if not gmail_email:
        raise HTTPException(status_code=400, detail="Missing gmail_email")

    result = await accounts_col.delete_one(
        {"user_id": user_id, "gmail_email": gmail_email}
    )

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")

    return {"message": "Account deleted successfully"}
