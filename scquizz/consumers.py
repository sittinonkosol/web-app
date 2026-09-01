import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

class QuizConsumer(AsyncWebsocketConsumer):
    GROUP_NAME = "quiz_room"
    active_user_count = 0

    async def connect(self):
        # Require authentication — unauthenticated connections are rejected
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        await self.channel_layer.group_add(
            self.GROUP_NAME,
            self.channel_name
        )
        await self.accept()

        QuizConsumer.active_user_count += 1
        await self.channel_layer.group_send(
            self.GROUP_NAME,
            {
                "type": "quiz.broadcast",
                "message": f"USERS:{QuizConsumer.active_user_count}"
            }
        )

    async def disconnect(self, close_code):
        # Only decrement counter if this connection was accepted (authenticated)
        if close_code != 4001:
            QuizConsumer.active_user_count = max(0, QuizConsumer.active_user_count - 1)
        await self.channel_layer.group_discard(
            self.GROUP_NAME,
            self.channel_name
        )
        if close_code != 4001:
            await self.channel_layer.group_send(
                self.GROUP_NAME,
                {
                    "type": "quiz.broadcast",
                    "message": f"USERS:{QuizConsumer.active_user_count}"
                }
            )

    async def receive(self, text_data=None, bytes_data=None):
        pass

    async def quiz_broadcast(self, event):
        message = event.get("message", "")
        await self.send(text_data=message)

def notify_update():
    """Helper to broadcast UPDATE signal to all connected clients (WebSocket & SSE)."""
    # 1. Notify WebSocket clients
    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                QuizConsumer.GROUP_NAME,
                {
                    "type": "quiz.broadcast",
                    "message": "UPDATE"
                }
            )
        except Exception:
            pass

    # 2. Notify SSE clients
    try:
        from .views import notify_sse_subscribers
        notify_sse_subscribers("UPDATE")
    except Exception:
        pass
