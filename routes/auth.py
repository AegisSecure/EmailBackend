# routes/auth.py
from fastapi import APIRouter, HTTPException,Depends
from pydantic import BaseModel
from passlib.context import CryptContext
import jwt
import os
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials 
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from passlib.context import CryptContext
from typing import Optional
import datetime

security = HTTPBearer()
load_dotenv()
from database import users_col ,auth_db,otps_col
from routes import otp#<--⭐️
#imporitng the database column for authorization purpose


router = APIRouter()
JWT_SECRET = os.getenv("JWT_SECRET", "supersecret")  
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class RegisterRequest(BaseModel):
    name:str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    token: str
    verified: bool


class SendOTPRequest(BaseModel):
    email: EmailStr

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str


class UserResponse(BaseModel):
    name: str
    email: str
    user_id: str


#--⭐️

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

class VerifyResetOTPRequest(BaseModel):
    email: EmailStr
    otp: str

class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str
    confirm_password: str


RESET_JWT_TTL_MINUTES = int(os.getenv("RESET_JWT_TTL_MINUTES", "15"))

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_reset_jwt(email: str) -> str:
    exp = datetime.datetime.utcnow() + datetime.timedelta(minutes=RESET_JWT_TTL_MINUTES)
    payload = {"sub": email, "purpose": "password_reset", "exp": exp}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    # pyjwt returns a str
    return token

def decode_reset_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # validate purpose claim
        if payload.get("purpose") != "password_reset":
            raise HTTPException(status_code=401, detail="Invalid token purpose")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Reset token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid reset token")

#--⭐️
    

# --------------------------
# Register endpoint
# --------------------------

    
@router.post("/register")
async def register_user(req: RegisterRequest):
    existing = await users_col.find_one({"email": req.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    # print("Raw request body:", body.decode())
    # print("Parsed:", req.dict())
    hashed_password = pwd_context.hash(req.password)
    user_doc = {
        "name": req.name,  # Added name field
        "email": req.email,
        "password": hashed_password,
        "verified": False,
        "user_id": str(datetime.datetime.now().timestamp())
    }
    await users_col.insert_one(user_doc)
    # return {"message": "User registered. OTP verification pending."}


    #<--⭐️
    otp_code = otp.generate_otp()
    await otp.store_otp(req.email, otp_code)
    sent = await otp.send_otp_email_async(req.email, otp_code)

    if sent:
        return {"message": "User registered. OTP sent to email."}
    else:
        # fallback for dev mode (no SMTP credentials)
        return {"message": f"User registered. OTP (dev mode): {otp_code}"}

# --------------------------
# Login endpoint
# --------------------------
@router.post("/login", response_model=LoginResponse)
async def login_user(req: LoginRequest):
    user = await users_col.find_one({"email": req.email})
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    
    if not pwd_context.verify(req.password, user["password"]):
        raise HTTPException(status_code=400, detail="Incorrect password")
    
    payload = {
        "email": user["email"],
        "user_id": str(user["_id"]),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=12)
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return {"token": token,"verified": user.get("verified", False)}





# -------- ⭐️

@router.post("/send-otp")
async def send_otp(req: SendOTPRequest):
    # Check if user exists
    user = await users_col.find_one({"email": req.email})
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    
    # Generate OTP
    otp_code = otp.generate_otp()
    
    # Store OTP in DB
    await otp.store_otp(req.email, otp_code)
    
    # Send OTP email
    sent = await otp.send_otp_email_async(req.email, otp_code)
    if sent:
        return {"message": "OTP sent to your email."}
    else:
        return {"message": f"OTP generated (dev mode): {otp_code}"}

@router.post("/verify-otp")
async def verify_otp(req: VerifyOTPRequest):
    print("📩 Incoming OTP verification request:", req.dict())  # Debug incoming payload

    try:
        is_valid = await otp.verify_otp_in_db(req.email, req.otp)
        print(f"🧩 OTP validation result for {req.email}: {is_valid}")

        if not is_valid:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP")

        await users_col.update_one({"email": req.email}, {"$set": {"verified": True}})
        print(f"✅ User {req.email} marked as verified")

        return {"message": "OTP verified successfully, user is now verified."}

    except Exception as e:
        print(f"❌ Exception during OTP verify: {e}")
        raise


def decode_jwt(token: str):
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return decoded
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/me")
async def get_user_info(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Returns the name and email of the logged-in user."""
    token = credentials.credentials
    decoded = decode_jwt(token)
    user = await users_col.find_one({"email": decoded["email"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "name": user["name"],
        "email": user["email"],
        "verified": user.get("verified", False),
    }



async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """A dependency to get the current user from a JWT token."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        email: str = payload.get("email")
        if email is None:
            raise HTTPException(status_code=403, detail="Invalid token payload")

        user = await users_col.find_one({"email": email})
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        user["user_id"] = str(user["_id"])
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=403, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Invalid token")
    
@router.post("/forgot-password")
async def forgot_password(req: SendOTPRequest):
    """Generate OTP and send to user's email if the user exists.
    Returns a generic message regardless of whether the email exists
    (to avoid user enumeration)."""
    email = req.email.lower()
    user = await users_col.find_one({"email": email})

    # If user exists -> store OTP & attempt to send email
    if user:
        otp_code = otp.generate_otp()
        await otp.store_otp(email, otp_code)
        sent = await otp.send_otp_email_async(email, otp_code)
        if sent:
            # generic success
            return {"message": "If this email is registered, an OTP has been sent."}
        else:
            # dev fallback: still generic, but helpful in dev logs
            print(f"[DEV] OTP for {email}: {otp_code}")
            return {"message": "If this email is registered, an OTP has been sent."}
    # If user doesn't exist, respond generically (do not store OTP)
    return {"message": "If this email is registered, an OTP has been sent."}

@router.post("/verify-reset-otp")
async def verify_reset_otp(req: VerifyResetOTPRequest):
    """Verify OTP for password reset. If valid, return a short-lived reset token."""
    email = req.email.lower()
    is_valid = await otp.verify_otp_in_db(email, req.otp)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # create and return reset JWT
    reset_token = create_reset_jwt(email)
    return {"reset_token": reset_token, "expires_in_minutes": RESET_JWT_TTL_MINUTES}

# @router.post("/reset-password")
# async def reset_password(data: dict):
#     email = data.get("email")
#     otp = data.get("otp")
#     new_password = data.get("new_password")

#     if not all([email, otp, new_password]):
#         raise HTTPException(status_code=400, detail="Missing fields")

#     # ✅ Verify OTP
#     otp_doc = await otp_col.find_one({"email": email, "otp": otp, "verified": True})
#     if not otp_doc:
#         raise HTTPException(status_code=400, detail="Invalid or unverified OTP")

#     # ✅ Hash and update password
#     hashed_pw = pwd_context.hash(new_password)
#     result = await users_col.update_one(
#         {"email": email},
#         {"$set": {"password": hashed_pw}}
#     )

#     if result.modified_count == 0:
#         raise HTTPException(status_code=404, detail="User not found")

#     # ✅ Clean OTP record
#     await otp_col.delete_many({"email": email})

#     return {"message": "Password updated successfully"}


@router.post("/reset-password")
async def reset_password(data: dict):
    email = data.get("email")
    otp = data.get("otp")
    new_password = data.get("new_password")

    if not all([email, otp, new_password]):
        raise HTTPException(status_code=400, detail="Missing fields")

    # ✅ Verify OTP (no need for "verified": True)
    otp_doc = await otps_col.find_one({"email": email, "otp": otp})
    if not otp_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # ✅ Hash and update password
    hashed_pw = pwd_context.hash(new_password)
    result = await users_col.update_one(
        {"email": email},
        {"$set": {"password": hashed_pw}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    await otps_col.delete_many({"email": email})
    return {"message": "Password updated successfully"}

