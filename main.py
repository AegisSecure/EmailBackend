from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# from routes import oauth
from dotenv import load_dotenv

load_dotenv()
from routes import auth, gmail,Oauth

app = FastAPI(title="Mail Backend")

# CORS for Flutter frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later replace with your Flutter URL
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(auth.router, prefix="/auth")
# app.include_router(gmail.router, prefix="/gmail")
app.include_router(gmail.router)
app.include_router(Oauth.router, prefix="/auth")
# app.include_router(oauth.router)
@app.get("/")
async def root():
    return {"message": "Mail Backend is running!"}
