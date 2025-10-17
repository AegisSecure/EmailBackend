from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from database import messages_col
import os
router = APIRouter()
JWT_SECRET = os.getenv("JWT_SECRET", "your_secret_key")
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# -----------------------
# Get current user ID from JWT
# -----------------------
async def get_current_user_id(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing user_id")
        return user_id
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# -----------------------
# Fetch emails for current user
# -----------------------
@router.get("/emails")
async def get_emails(user_id: str = Depends(get_current_user_id)):
    try:
        emails_cursor = messages_col.find({"user_id": user_id}, {"_id": 0})
        emails = await emails_cursor.to_list(length=None)
        return sorted(emails, key=lambda e: e.get("date", ""), reverse=True)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
