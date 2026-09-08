import logging

from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError

from django_tenants.utils import schema_context

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

from urllib.parse import parse_qs

from tenant.models import Domain, Tenant
from utils.custom_authentication import CustomJWTAuthentication

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        print("========== WEBSOCKET CONNECT ==========")
        print("PATH:", self.scope.get("path"))
        print("QUERY_STRING:", self.scope.get("query_string"))
        print("USER:", self.scope.get("user"))
        print("TENANT:", self.scope.get("tenant"))
        print("HEADERS:", self.scope.get("headers"))
        query_string = self.scope["query_string"].decode()
        token = parse_qs(query_string).get("token", [None])[0]

        print("WS QUERY STRING:", self.scope.get("query_string"))
        print("WS HEADERS:", self.scope.get("headers"))

        if not token:
            await self.close()
            return

        host = self.get_host()

        print("HOST:", host)
        tenant_schema = self.scope.get("url_route", {}).get("kwargs", {}).get(
            "tenant_schema"
        )
        print("TENANT SCHEMA:", tenant_schema)
        authenticated = await self.authenticate_token(
            token, host, tenant_schema
        )
        print("AUTHENTICATED:", authenticated)
        if authenticated is None:
            await self.close()
            return
       
        self.user, self.schema_name = authenticated

        print("USER:", self.user)
        print("SCHEMA NAME:", self.schema_name)
    
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
    def authenticate_token(self, token, host, tenant_schema=None):
        try:
            with schema_context("public"):
                authentication = CustomJWTAuthentication()
                validated_token = authentication.get_validated_token(token)
                token_schema_name = validated_token.payload.get("schema_name")
                if not token_schema_name:
                    return None

                if tenant_schema and tenant_schema != token_schema_name:
                    return None

                tenant = Tenant.objects.get(schema_name=token_schema_name)

                if host:
                    domain = Domain.objects.filter(domain=host).select_related(
                        "tenant"
                    ).first()
                    if domain and domain.tenant.schema_name != token_schema_name:
                        return None

                authentication.check_schema_name(
                    validated_token.payload, tenant.schema_name
                )

            with schema_context(tenant.schema_name):
                user = authentication.get_user(validated_token)

            return user, tenant.schema_name
        except Exception as error:
            logger.exception("========== WEBSOCKET AUTH ERROR ==========")
            logger.exception("ERROR TYPE: %s", type(error).__name__)
            logger.exception("ERROR: %s", error)
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