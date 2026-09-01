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

    async def tail_log(self):
        # We need synchronous DB call wrapped in sync_to_async to get the path
        # But we can hardcode it to '/wdc/papermc/logs/latest.log' as per the plan to avoid DB hit.
        log_path = '/wdc/papermc/logs/latest.log'
        
        if not os.path.exists(log_path):
            await self.send(text_data="Log file not found. Waiting for server to start...\n")
            # Wait for file to be created
            while not os.path.exists(log_path):
                await asyncio.sleep(5)
                
        try:
            # We use tail -n 50 -f
            process = await asyncio.create_subprocess_exec(
                'tail', '-n', '50', '-f', log_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            while True:
                line = await process.stdout.readline()
                if line:
                    await self.send(text_data=line.decode('utf-8', errors='ignore'))
                else:
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            if 'process' in locals():
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
            raise
