from fastapi import FastAPI, WebSocket, WebSocketDisconnect, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi import WebSocket
from database import avatars_col
from websocket_manager import connect, disconnect
from routes import auth, gmail, Oauth,notifications,sms,analysis,dashboard

load_dotenv()
app = FastAPI(title="Mail Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth")
app.include_router(gmail.router)
app.include_router(Oauth.router)
app.include_router(Oauth.router, prefix="/auth")
app.include_router(notifications.router)
app.include_router(analysis.router)
app.include_router(sms.router, prefix="/sms", tags=["SMS"])
app.include_router(dashboard.router)

ws_router = APIRouter()


@app.on_event("startup")
async def init_indexes():
    await avatars_col.create_index("email", unique=True)

@app.websocket("/ws/emails")
async def websocket_endpoint(websocket: WebSocket):
    """Handle real-time email update connections."""
    await connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        await disconnect(websocket)

@app.websocket("/ws/sms")
async def websocket_sms_endpoint(websocket: WebSocket):
    """Handle real-time SMS update connections."""
    await connect(websocket)
    try:
        while True:
            await websocket.receive_text()  
    except WebSocketDisconnect:
        await disconnect(websocket)
    except Exception as e:
        print(f"WebSocket SMS error: {e}")
        await disconnect(websocket)

@app.get("/")
async def root():
    return {"message": "Mail Backend is running and WebSocket ready!"}