import os
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import ServerSetting

class LogConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        # For simplicity, we just check if authenticated, you can add more checks later
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        await self.accept()
        
        # Start background task to tail log
        self.tail_task = asyncio.create_task(self.tail_log())

    async def disconnect(self, close_code):
        if hasattr(self, 'tail_task'):
            self.tail_task.cancel()

    async def receive(self, text_data=None, bytes_data=None):
        if text_data == 'ping':
            await self.send(text_data='pong')

    async def tail_log(self):
        log_path = '/wdc/PaperMC/logs/latest.log'
        
        while not os.path.exists(log_path):
            await self.send(text_data="Waiting for Minecraft server log...\n")
            await asyncio.sleep(2)

        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Read recent 30KB as initial buffer so user sees recent activity
                file_size = os.path.getsize(log_path)
                init_seek = max(0, file_size - 30000)
                f.seek(init_seek, os.SEEK_SET)
                if init_seek > 0:
                    f.readline() # Discard partial first line
                
                initial_data = f.read()
                if initial_data:
                    filtered_initial = '\n'.join(line for line in initial_data.split('\n') if 'Thread RCON Client' not in line)
                    if filtered_initial.strip():
                        await self.send(text_data=filtered_initial + '\n')
                last_pos = f.tell()
                
                # Stream ONLY newly appended lines
                while True:
                    if os.path.exists(log_path):
                        current_size = os.path.getsize(log_path)
                        if current_size < last_pos:
                            # Log was truncated/cleared (e.g. server restarted)
                            f.seek(0, os.SEEK_SET)
                        
                        new_data = f.read()
                        if new_data:
                            last_pos = f.tell()
                            filtered_new = '\n'.join(line for line in new_data.split('\n') if 'Thread RCON Client' not in line)
                            if filtered_new.strip():
                                await self.send(text_data=filtered_new + '\n')
                    
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            try:
                await self.send(text_data=f"\n[Log Stream Notice: {e}]\n")
            except Exception:
                pass
