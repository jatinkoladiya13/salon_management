from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError

from django_tenants.utils import schema_context
from django.contrib.auth import get_user_model

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

from urllib.parse import parse_qs

from tenant.models import Domain
from utils.custom_authentication import CustomJWTAuthentication


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        query_string = self.scope["query_string"].decode()
        token = parse_qs(query_string).get("token", [None])[0]

        if not token:
            await self.close()
            return
        
        authenticated = await self.authenticate_token(token, self.get_host())
        if authenticated is None:
            await self.close()
            return

        self.user, self.schema_name = authenticated
    
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

    def get_host(self):
        for header_name, header_value in self.scope.get("headers", []):
            if header_name == b"host":
                return header_value.decode().split(":", 1)[0].lower()
        return None

    @database_sync_to_async
    def authenticate_token(self, token, host):
        if not host:
            return None

        try:
            with schema_context("public"):
                domain = Domain.objects.select_related("tenant").get(domain=host)
                tenant = domain.tenant

                authentication = CustomJWTAuthentication()
                validated_token = authentication.get_validated_token(token)
                authentication.check_schema_name(
                    validated_token.payload, tenant.schema_name
                )

            with schema_context(tenant.schema_name):
                user = authentication.get_user(validated_token)

            return user, tenant.schema_name
        except (AuthenticationFailed, Domain.DoesNotExist, InvalidToken, TokenError):
            return None
        
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