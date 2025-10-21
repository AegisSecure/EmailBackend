# websocket_manager.py
from fastapi import WebSocket
active_connections = []

async def connect(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)

async def disconnect(websocket: WebSocket):
    active_connections.remove(websocket)

async def broadcast_new_email(gmail_email: str):
    message = {"new_email": True, "gmail_email": gmail_email}
    print(f"📢 Broadcasting: {message}")
    for conn in active_connections:
        await conn.send_json(message)
