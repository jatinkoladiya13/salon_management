import logging

from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError

from django_tenants.utils import get_public_schema_name, schema_context

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

from urllib.parse import parse_qs

from tenant.models import Domain, Tenant
from utils.custom_authentication import CustomJWTAuthentication

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        query_string = self.scope["query_string"].decode()
        token = parse_qs(query_string).get("token", [None])[0]

        if not token:
            logger.warning("WebSocket rejected: missing token")
            await self.close()
            return

        host = self.get_host()
        tenant_schema = self.scope.get("url_route", {}).get("kwargs", {}).get(
            "tenant_schema"
        )
        authenticated = await self.authenticate_token(
            token, host, tenant_schema
        )
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
    def authenticate_token(self, token, host, tenant_schema=None):
        try:
            with schema_context("public"):
                authentication = CustomJWTAuthentication()
                validated_token = authentication.get_validated_token(token)
                token_schema_name = validated_token.payload.get("schema_name")
                if not token_schema_name:
                    logger.warning("WebSocket rejected: token has no schema_name")
                    return None

                if tenant_schema and tenant_schema != token_schema_name:
                    logger.warning(
                        "WebSocket rejected: URL schema does not match token schema"
                    )
                    return None

                try:
                    tenant = Tenant.objects.get(schema_name=token_schema_name)
                except Tenant.DoesNotExist:
                    logger.warning(
                        "WebSocket rejected: tenant schema %r does not exist",
                        token_schema_name,
                    )
                    return None

                # Tenants are resolved from the signed token (and the
                # optional URL prefix), never from the hostname - every tenant
                # is served from the same host in this deployment. Only a
                # host that is a tenant's *own* domain may contradict the
                # token; a shared host (bare IP, public domain) carries no
                # tenant information and must not veto it.
                if host:
                    domain = Domain.objects.filter(domain=host).select_related(
                        "tenant"
                    ).first()
                    if (
                        domain
                        and domain.tenant.schema_name != get_public_schema_name()
                        and domain.tenant.schema_name != token_schema_name
                    ):
                        logger.warning(
                            "WebSocket rejected: host %r belongs to schema %r, not %r",
                            host,
                            domain.tenant.schema_name,
                            token_schema_name,
                        )
                        return None

                authentication.check_schema_name(
                    validated_token.payload, tenant.schema_name
                )

            with schema_context(tenant.schema_name):
                user = authentication.get_user(validated_token)

            return user, tenant.schema_name
        except (AuthenticationFailed, InvalidToken, TokenError) as error:
            logger.warning(
                "WebSocket rejected during token authentication: %s: %s",
                type(error).__name__,
                error,
            )
            return None
        except Exception:
            logger.exception("Unexpected WebSocket authentication error")
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