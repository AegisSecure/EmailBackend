from fastapi import WebSocket
from typing import List, Dict, Any

active_connections: List[WebSocket] = []
async def connect(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    print(f"Connected: {len(active_connections)} active connection(s)")

async def disconnect(websocket: WebSocket):
    if websocket in active_connections:
        active_connections.remove(websocket)
    print(f"Disconnected: {len(active_connections)} active connection(s)")


async def broadcast_new_email(gmail_email: str, extra_data: Dict[str, Any] = None):
    message = {"new_email": True, "gmail_email": gmail_email}
    if extra_data:
        message.update(extra_data)

    # print(f"Broadcasting: {message}")
    disconnected = []
    for conn in active_connections:
        try:
            await conn.send_json(message)
        except Exception as e:
            # print(f"WebSocket send failed: {e}")
            disconnected.append(conn)
    for conn in disconnected:
        await disconnect(conn)