from typing import Dict, List, Any
from fastapi import WebSocket
from loguru import logger
import json

class ConnectionManager:
    def __init__(self):
        # active_connections: { user_id: [websocket1, websocket2] }
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # org_connections: { org_id: [websocket1, websocket2] }
        self.org_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str, organization_id: str):
        # Only accept if not already accepted (prevents RuntimeError)
        if websocket.client_state.name == 'CONNECTING':
            await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        
        if organization_id not in self.org_connections:
            self.org_connections[organization_id] = []
        self.org_connections[organization_id].append(websocket)
        
        logger.info(f"🔌 [WEBSOCKET] Connected user: {user_id} (Org: {organization_id})")

    def disconnect(self, websocket: WebSocket, user_id: str, organization_id: str):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        if organization_id in self.org_connections:
            if websocket in self.org_connections[organization_id]:
                self.org_connections[organization_id].remove(websocket)
            if not self.org_connections[organization_id]:
                del self.org_connections[organization_id]
                
        logger.info(f"🔌 [WEBSOCKET] Disconnected user: {user_id}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast_to_user(self, user_id: str, message: Dict[str, Any]):
        if user_id in self.active_connections:
            data = json.dumps(message)
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_text(data)
                except Exception as e:
                    logger.error(f"❌ [WEBSOCKET] Failed broadcast to {user_id}: {e}")

    async def broadcast_to_organization(self, organization_id: str, message: Dict[str, Any]):
        if organization_id in self.org_connections:
            data = json.dumps(message)
            for connection in self.org_connections[organization_id]:
                try:
                    await connection.send_text(data)
                except Exception as e:
                    logger.error(f"❌ [WEBSOCKET] Failed broadcast to org {organization_id}: {e}")

manager = ConnectionManager()
