from django.urls import re_path
from appointment.consumers import NotificationConsumer




websocket_urlpatterns = [
    re_path("ws/notifications/", NotificationConsumer.as_asgi())
    
]