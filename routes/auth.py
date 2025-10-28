# routes/auth.py
from fastapi import APIRouter, HTTPException,Depends
from pydantic import BaseModel
from passlib.context import CryptContext
import jwt
import os
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
import datetime

load_dotenv()
from database import users_col ,auth_db 
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


class SendOTPRequest(BaseModel):#<--⭐️
    email: EmailStr

class VerifyOTPRequest(BaseModel):#<--⭐️
    email: EmailStr
    otp: str

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
