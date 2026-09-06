import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "salon_management.settings")

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

django_asgi_app = get_asgi_application()

from .routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # "websocket": AllowedHostsOriginValidator(
        #     AuthMiddlewareStack(
        #         URLRouter(websocket_urlpatterns)
        #     )
        # ),
        "websocket": AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    }
)