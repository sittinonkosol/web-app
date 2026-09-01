from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/mc/logs/', consumers.ConsoleConsumer.as_asgi()),
    path('ws/mc/console/', consumers.ConsoleConsumer.as_asgi()),
]
