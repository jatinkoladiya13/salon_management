from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from django.contrib.auth.models import AnonymousUser
from django_tenants.utils import schema_context
from django.contrib.auth import get_user_model

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

from urllib.parse import parse_qs
import json


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        query_string = self.scope["query_string"].decode()
        token = parse_qs(query_string).get("token", [None])[0]

        if not token:
            await self.close()
            return
        
        try:
            access_token = AccessToken(token)

            user_id = access_token["user_id"]
            schema_name = access_token.get("schema_name", "public")
             
            user = await self.get_user(user_id, schema_name)

            if not user:
                await self.close()
                return

            self.user = user 
            self.schema_name = schema_name

        except (InvalidToken, TokenError):
            await self.close()
            return
    
        self.room_group_name = f"notification_{self.schema_name}_{self.user.id}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        
        await self.accept()
        await self.send_json({
            "type": "connection",
            "status": "connected",
            "user_id": str(self.user.id),
            "message": "WebSocket connected successfully",
        })
       
    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )
            print(f"WebSocket disconnected for user {self.user.id}")

    @database_sync_to_async
    def get_user(self, user_id, schema_name):
        with schema_context(schema_name):
            User = get_user_model()
            return User.objects.filter(id=user_id).first()
        
    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        if action == "ping":
            await self.send_json({"type": "pong"})
        else:
            await self.send_json({
                "type": "error",
                "message": f"Unknown message type: {action}"
            })

    # This method is called when a message is sent to the group
    async def send_notification(self, event):
        # Send message to WebSocket
        await self.send_json(event["data"])
        print(f"Sent notification to user {self.user.id}")