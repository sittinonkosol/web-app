import os
import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from core.permissions import get_user_app_role
from .models import ServerSetting
from .utils import send_rcon_command

class ConsoleConsumer(AsyncWebsocketConsumer):
    active_clients = set()

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        self.role = await database_sync_to_async(get_user_app_role)(self.user, 'mcmanager')
        if self.role == 'none':
            await self.close(code=4003)
            return

        await self.accept()
        ConsoleConsumer.active_clients.add(self)

        # Send initial connection banner
        username = getattr(self.user, 'username', 'Admin')
        banner = (
            f"\x1b[36m[Console] Connected to Minecraft Interactive Console as \x1b[32m{username}\x1b[36m ({self.role.upper()})\x1b[0m\n"
        )
        await self.send(text_data=json.dumps({
            "type": "console_message",
            "message": banner
        }))

        # Send initial recent logs from latest.log
        await self.send_initial_log_buffer()

        # Start tailing task for server logs
        self.tail_task = asyncio.create_task(self.tail_log())

    async def disconnect(self, close_code):
        ConsoleConsumer.active_clients.discard(self)
        if hasattr(self, 'tail_task'):
            self.tail_task.cancel()

    @classmethod
    async def broadcast(cls, payload):
        """Broadcasts payload to all currently connected console clients without Redis dependency."""
        dead_clients = []
        for client in list(cls.active_clients):
            try:
                await client.send(text_data=json.dumps(payload))
            except Exception:
                dead_clients.append(client)
        for dead in dead_clients:
            cls.active_clients.discard(dead)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        if text_data == 'ping':
            await self.send(text_data='pong')
            return

        # Parse command payload
        command = None
        try:
            payload = json.loads(text_data)
            if isinstance(payload, dict):
                command = payload.get('command') or payload.get('message') or payload.get('cmd')
        except (json.JSONDecodeError, TypeError):
            command = text_data.strip()

        if not command:
            return

        command = command.strip()
        if command.startswith('/'):
            command = command[1:].strip()

        if not command:
            return

        # Permission check: viewer cannot execute commands
        if self.role not in ['admin', 'moderator']:
            await self.send(text_data=json.dumps({
                "type": "console_message",
                "message": "\x1b[31m[Permission Denied] You must have admin/moderator permissions to execute console commands.\x1b[0m\n"
            }))
            return

        username = getattr(self.user, 'username', 'Console')

        # 1. Broadcast command input prompt to all connected users
        cmd_echo = f"\x1b[32m> \x1b[1m{command}\x1b[0m \x1b[90m(by {username})\x1b[0m\n"
        await ConsoleConsumer.broadcast({
            "type": "console_message",
            "message": cmd_echo,
            "is_command": True,
            "command": command
        })

        # 2. Execute command via RCON asynchronously
        response = await self.execute_mc_command(command)

        # 3. Broadcast server response if any
        if response:
            resp_lines = response.strip().split('\n')
            formatted_resp = '\n'.join(f"\x1b[37m< {line}\x1b[0m" for line in resp_lines) + '\n'
            await ConsoleConsumer.broadcast({
                "type": "console_message",
                "message": formatted_resp,
                "is_response": True
            })

    @database_sync_to_async
    def execute_mc_command(self, command):
        try:
            settings = ServerSetting.get_settings()
            return send_rcon_command(command, port=settings.rcon_port, password=settings.rcon_password)
        except Exception as e:
            return f"\x1b[31m[RCON Execution Error]: {str(e)}\x1b[0m"

    async def send_initial_log_buffer(self):
        log_path = '/wdc/PaperMC/logs/latest.log'
        if not os.path.exists(log_path):
            await self.send(text_data=json.dumps({
                "type": "console_message",
                "message": "\x1b[33m[Console] Waiting for Minecraft server to generate logs...\x1b[0m\n"
            }))
            return

        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                file_size = os.path.getsize(log_path)
                init_seek = max(0, file_size - 35000)
                f.seek(init_seek, os.SEEK_SET)
                if init_seek > 0:
                    f.readline()  # discard partial first line

                initial_data = f.read()
                if initial_data:
                    lines = [
                        line for line in initial_data.split('\n')
                        if 'Thread RCON Client' not in line
                    ]
                    filtered_initial = '\n'.join(lines).strip()
                    if filtered_initial:
                        await self.send(text_data=json.dumps({
                            "type": "console_message",
                            "message": filtered_initial + '\n',
                            "is_initial": True
                        }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                "type": "console_message",
                "message": f"\x1b[31m[Log Load Error: {e}]\x1b[0m\n"
            }))

    async def tail_log(self):
        log_path = '/wdc/PaperMC/logs/latest.log'

        # Wait until file exists
        while not os.path.exists(log_path):
            await asyncio.sleep(2)

        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(0, os.SEEK_END)
                last_pos = f.tell()

                while True:
                    if os.path.exists(log_path):
                        current_size = os.path.getsize(log_path)
                        if current_size < last_pos:
                            # Log file was truncated or server restarted
                            f.seek(0, os.SEEK_SET)
                            last_pos = 0

                        new_data = f.read()
                        if new_data:
                            last_pos = f.tell()
                            lines = [
                                line for line in new_data.split('\n')
                                if 'Thread RCON Client' not in line
                            ]
                            filtered_new = '\n'.join(lines).strip()
                            if filtered_new:
                                await self.send(text_data=json.dumps({
                                    "type": "console_message",
                                    "message": filtered_new + '\n'
                                }))

                    await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            try:
                await self.send(text_data=json.dumps({
                    "type": "console_message",
                    "message": f"\x1b[31m[Console Stream Notice: {e}]\x1b[0m\n"
                }))
            except Exception:
                pass

# Backward compatibility alias
LogConsumer = ConsoleConsumer
