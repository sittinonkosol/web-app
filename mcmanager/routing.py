from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/mc/logs/', consumers.LogConsumer.as_asgi()),
]
