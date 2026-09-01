import os
import re
import json
import time
import uuid
import socket
import struct
import select
import tarfile
import shutil
import psutil
import subprocess
from datetime import datetime, timezone, timedelta

class ThreadSafeMCRcon:
    """
    Pure Python Thread-Safe RCON client using standard socket timeouts
    instead of signal.alarm (which crashes in non-main threads like Daphne/ASGI).
    """
    def __init__(self, host, password, port=25575, timeout=5):
        self.host = host
        self.password = password
        self.port = int(port)
        self.timeout = timeout
        self.sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        self._send(3, self.password)

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _read(self, length):
        data = b""
        while len(data) < length:
            chunk = self.sock.recv(length - len(data))
            if not chunk:
                raise ConnectionError("RCON connection closed by server")
            data += chunk
        return data

    def _send(self, out_type, out_data):
        if not self.sock:
            raise ConnectionError("Must connect before sending data")
        out_payload = struct.pack("<ii", 0, out_type) + out_data.encode('utf-8') + b"\x00\x00"
        out_length = struct.pack("<i", len(out_payload))
        self.sock.sendall(out_length + out_payload)

        in_data = ""
        while True:
            (in_length,) = struct.unpack("<i", self._read(4))
            in_payload = self._read(in_length)
            in_id, in_type = struct.unpack("<ii", in_payload[:8])
            in_data_partial = in_payload[8:-2]
            in_padding = in_payload[-2:]
            if in_padding != b"\x00\x00":
                raise ValueError("Incorrect RCON padding")
            if in_id == -1:
                raise PermissionError("RCON authentication failed: invalid password")
            in_data += in_data_partial.decode('utf-8', errors='replace')
            r, _, _ = select.select([self.sock], [], [], 0)
            if not r:
                return in_data

    def command(self, cmd):
        result = self._send(2, cmd)
        time.sleep(0.003)
        return result

def get_max_allowed_ram_mb():
    total_ram_bytes = psutil.virtual_memory().total
    total_ram_mb = total_ram_bytes / (1024 * 1024)
    allowed_mb = total_ram_mb - 6144
    return max(1024, int(allowed_mb))

def parse_server_properties(filepath):
    if not os.path.exists(filepath):
        return {}
    config = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                config[key.strip()] = value.strip()
    return config

def save_server_properties(filepath, config_dict):
    if not os.path.exists(filepath):
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("# Minecraft server properties\n")
            
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    updated_keys = set()
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            key, _, _ = stripped.partition('=')
            key = key.strip()
            if key in config_dict:
                new_lines.append(f"{key}={config_dict[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
            
    for key, value in config_dict.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")
            
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

def get_service_status(service_name):
    try:
        result = subprocess.run(['sudo', '-n', 'systemctl', 'is-active', service_name], capture_output=True, text=True)
        return result.stdout.strip() == 'active'
    except Exception:
        return False

def control_service(service_name, action):
    if action not in ['start', 'stop', 'restart']:
        return False, "Invalid action"
    try:
        result = subprocess.run(['sudo', '-n', 'systemctl', action, service_name], capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stderr.strip() or result.stdout.strip() or "systemctl failed"
        return True, ""
    except Exception as e:
        return False, str(e)

def reset_world(server_path):
    control_service('papermc', 'stop')
    success = True
    errors = []
    
    for folder in ['world', 'world_nether', 'world_the_end']:
        folder_path = os.path.join(server_path, folder)
        if os.path.exists(folder_path):
            try:
                shutil.rmtree(folder_path)
            except Exception as e:
                success = False
                errors.append(str(e))
                
    if not success:
        return False, f"Failed to delete folders: {', '.join(errors)}"
    return True, ""

def get_java_resource_usage():
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            if 'java' in proc.info['name'].lower() and proc.info['cmdline'] and 'paper' in ' '.join(proc.info['cmdline']).lower():
                cpu = round(proc.cpu_percent(interval=0.1) / psutil.cpu_count(), 1)
                mem = proc.memory_info().rss / (1024 * 1024)
                uptime_sec = int(time.time() - proc.info['create_time'])
                
                # Format uptime
                h, rem = divmod(uptime_sec, 3600)
                m, s = divmod(rem, 60)
                uptime_str = f"{h}h {m}m" if h > 0 else f"{m}m {s}s"
                
                return {"cpu_percent": cpu, "ram_mb": mem, "uptime": uptime_str}
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return {"cpu_percent": 0.0, "ram_mb": 0.0, "uptime": "Offline"}

def send_rcon_command(command, host='127.0.0.1', port=25575, password=''):
    if not password:
        return "Error: RCON password not configured."
    try:
        with ThreadSafeMCRcon(host, password, port=port, timeout=4) as mcr:
            resp = mcr.command(command)
            return resp
    except Exception as e:
        return f"RCON Error: {str(e)}"

# ============================================================
# Player Management Utilities
# ============================================================

def _read_json_file(filepath, default=[]):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def query_minecraft_slp(host='127.0.0.1', port=25565):
    """Query Minecraft Server List Ping (SLP) for real-time online players without needing RCON."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        s.connect((host, port))
        
        host_bytes = host.encode('utf-8')
        handshake = b'\x00' + b'\xff\x05' + struct.pack('>B', len(host_bytes)) + host_bytes + struct.pack('>H', port) + b'\x01'
        s.sendall(struct.pack('>B', len(handshake)) + handshake)
        s.sendall(b'\x01\x00')
        
        def read_varint():
            val = 0
            for i in range(5):
                b = s.recv(1)
                if not b:
                    return 0
                byte = b[0]
                val |= (byte & 0x7F) << (7 * i)
                if not (byte & 0x80):
                    break
            return val
            
        packet_len = read_varint()
        packet_id = read_varint()
        json_len = read_varint()
        data = b''
        while len(data) < json_len:
            chunk = s.recv(min(4096, json_len - len(data)))
            if not chunk:
                break
            data += chunk
        s.close()
        return json.loads(data.decode('utf-8', errors='replace'))
    except Exception:
        return {}

def get_player_ping(player_name, host='127.0.0.1', port=25575, password=''):
    """Query player in-game latency via RCON ping command."""
    if not password:
        return None
    try:
        resp = send_rcon_command(f"ping {player_name}", host=host, port=port, password=password)
        if resp and not resp.startswith("Error:") and not resp.startswith("RCON Error"):
            m = re.search(r'(\d+)\s*ms', resp, re.IGNORECASE)
            if m:
                return int(m.group(1))
            m = re.search(r'is\s+(\d+)', resp, re.IGNORECASE)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return None

_fallback_session_starts = {}

def get_player_join_times(server_path):
    global _fallback_session_starts
    log_path = os.path.join(server_path, 'logs', 'latest.log')
    join_times = {}
    now_utc = datetime.now(timezone.utc)
    
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    m_join = re.search(r'\[(\d{2}):(\d{2}):(\d{2})\].*?:\s+([a-zA-Z0-9_\-]+)\s+joined the game', line)
                    if m_join:
                        h, m, s, name = int(m_join.group(1)), int(m_join.group(2)), int(m_join.group(3)), m_join.group(4)
                        dt_utc = datetime(now_utc.year, now_utc.month, now_utc.day, h, m, s, tzinfo=timezone.utc)
                        if dt_utc > now_utc:
                            dt_utc = dt_utc - timedelta(days=1)
                        join_times[name] = dt_utc.timestamp()
                    m_left = re.search(r'\[(\d{2}):(\d{2}):(\d{2})\].*?:\s+([a-zA-Z0-9_\-]+)\s+left the game', line)
                    if m_left:
                        name = m_left.group(4)
                        join_times.pop(name, None)
                        _fallback_session_starts.pop(name, None)
        except Exception:
            pass
    return join_times

def format_time_duration(seconds):
    if seconds is None or seconds < 0:
        return ""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m" if m > 0 else f"{h}h"
    else:
        d = seconds // 86400
        h = (seconds % 86400) // 3600
        return f"{d}d {h}h" if h > 0 else f"{d}d"

def get_player_last_seen(server_path):
    usercache_path = os.path.join(server_path, 'usercache.json')
    usercache = _read_json_file(usercache_path, [])
    name_to_uuid = {entry.get('name'): entry.get('uuid') for entry in usercache if entry.get('name') and entry.get('uuid')}
    
    last_seen = {}
    data_dirs = [
        os.path.join(server_path, 'world', 'players', 'data'),
        os.path.join(server_path, 'world', 'players', 'stats'),
        os.path.join(server_path, 'world', 'playerdata'),
        os.path.join(server_path, 'world', 'stats'),
    ]
    for name, uuid in name_to_uuid.items():
        latest_mtime = 0
        for d in data_dirs:
            for ext in ['.dat', '.json']:
                fp = os.path.join(d, f"{uuid}{ext}")
                if os.path.exists(fp):
                    try:
                        mtime = os.path.getmtime(fp)
                        if mtime > latest_mtime:
                            latest_mtime = mtime
                    except Exception:
                        pass
        if latest_mtime > 0:
            last_seen[name] = latest_mtime
    return last_seen

def get_players_data(server_path, host='127.0.0.1', port=25575, game_port=25565, password=''):
    # 1. Parse JSON files
    ops_list = _read_json_file(os.path.join(server_path, 'ops.json'), [])
    whitelist = _read_json_file(os.path.join(server_path, 'whitelist.json'), [])
    banned_players = _read_json_file(os.path.join(server_path, 'banned-players.json'), [])
    usercache = _read_json_file(os.path.join(server_path, 'usercache.json'), [])
    
    op_names = {entry.get('name') for entry in ops_list if entry.get('name')}
    wl_names = {entry.get('name') for entry in whitelist if entry.get('name')}
    banned_names = {entry.get('name') for entry in banned_players if entry.get('name')}
    
    # 2. Get online players via Minecraft SLP (port 25565) & RCON (port 25575)
    online_names = set()
    slp_online_count = 0
    if get_service_status('papermc'):
        # A. Query SLP directly on Minecraft game port (25565)
        slp_data = query_minecraft_slp(host=host, port=game_port)
        if slp_data and 'players' in slp_data:
            players_obj = slp_data['players']
            slp_online_count = players_obj.get('online', 0)
            for sample in players_obj.get('sample', []):
                if sample.get('name'):
                    online_names.add(sample['name'])
                    
        # B. Fallback to RCON only if SLP returned no samples but reported online > 0
        if not online_names and slp_online_count > 0 and password:
            try:
                rcon_resp = send_rcon_command("list", host=host, port=port, password=password)
                if rcon_resp and ":" in rcon_resp and not rcon_resp.startswith("Error:") and not rcon_resp.startswith("RCON Error"):
                    _, _, names_part = rcon_resp.partition(":")
                    for name in names_part.split(","):
                        clean_name = name.strip()
                        if clean_name:
                            online_names.add(clean_name)
            except Exception:
                pass

    tunnel_ping = get_tunnel_ping("jakarta-baghdad.tun.ply.gg")
    default_online_ping = int(round(tunnel_ping)) if tunnel_ping is not None else 38

    # 4. Combine all known players & calculate session durations
    all_names = set(online_names) | op_names | wl_names | banned_names
    for entry in usercache:
        if entry.get('name'):
            all_names.add(entry.get('name'))
            
    join_times = get_player_join_times(server_path)
    last_seen_times = get_player_last_seen(server_path)
    now = time.time()

    players = []
    for name in all_names:
        is_online = name in online_names
        p_ping = default_online_ping if is_online else None
        
        session_duration = 0
        last_seen_ts = last_seen_times.get(name, 0)
        time_text = ""
        
        if is_online:
            if name in join_times:
                session_duration = max(0, int(now - join_times[name]))
            else:
                if name not in _fallback_session_starts:
                    _fallback_session_starts[name] = now
                session_duration = max(0, int(now - _fallback_session_starts[name]))
            time_text = format_time_duration(session_duration)
        else:
            _fallback_session_starts.pop(name, None)
            if last_seen_ts > 0:
                ago_sec = max(0, int(now - last_seen_ts))
                time_text = f"{format_time_duration(ago_sec)} ago"

        players.append({
            "name": name,
            "online": is_online,
            "ping": p_ping,
            "session_duration": session_duration,
            "last_seen": last_seen_ts,
            "time_text": time_text,
            "is_op": name in op_names,
            "is_whitelisted": name in wl_names,
            "is_banned": name in banned_names,
        })
        
    # Sort:
    # 1. Online players first (group 0), longest online first (-session_duration)
    # 2. Offline players second (group 1), most recently online first (-last_seen)
    def sort_player_key(p):
        if p['online']:
            return (0, -(p.get('session_duration') or 0), 0, p['name'].lower())
        else:
            return (1, 0, -(p.get('last_seen') or 0), p['name'].lower())

    players.sort(key=sort_player_key)
        
    actual_online_count = max(len(online_names), slp_online_count)
    return {
        "players": players,
        "online_count": actual_online_count,
        "total_known": len(players)
    }

def _write_json_file(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False

def _get_player_uuid(server_path, player_name):
    usercache = _read_json_file(os.path.join(server_path, 'usercache.json'), [])
    for entry in usercache:
        if entry.get('name', '').lower() == player_name.lower():
            return entry.get('uuid')
    return str(uuid.uuid3(uuid.NAMESPACE_DNS, f"OfflinePlayer:{player_name}"))

def _apply_player_action_offline(server_path, action, player_name):
    p_uuid = _get_player_uuid(server_path, player_name)
    
    if action == 'op':
        ops_path = os.path.join(server_path, 'ops.json')
        ops = _read_json_file(ops_path, [])
        if not any(entry.get('name', '').lower() == player_name.lower() for entry in ops):
            ops.append({
                "uuid": p_uuid,
                "name": player_name,
                "level": 4,
                "bypassesPlayerLimit": False
            })
            _write_json_file(ops_path, ops)
        return True, f"Made {player_name} a server operator (OP)"

    elif action == 'deop':
        ops_path = os.path.join(server_path, 'ops.json')
        ops = _read_json_file(ops_path, [])
        ops = [entry for entry in ops if entry.get('name', '').lower() != player_name.lower()]
        _write_json_file(ops_path, ops)
        return True, f"Removed operator status from {player_name}"

    elif action == 'whitelist_add':
        wl_path = os.path.join(server_path, 'whitelist.json')
        wl = _read_json_file(wl_path, [])
        if not any(entry.get('name', '').lower() == player_name.lower() for entry in wl):
            wl.append({"uuid": p_uuid, "name": player_name})
            _write_json_file(wl_path, wl)
        return True, f"Added {player_name} to whitelist"

    elif action == 'whitelist_remove':
        wl_path = os.path.join(server_path, 'whitelist.json')
        wl = _read_json_file(wl_path, [])
        wl = [entry for entry in wl if entry.get('name', '').lower() != player_name.lower()]
        _write_json_file(wl_path, wl)
        return True, f"Removed {player_name} from whitelist"

    elif action == 'ban':
        ban_path = os.path.join(server_path, 'banned-players.json')
        bans = _read_json_file(ban_path, [])
        if not any(entry.get('name', '').lower() == player_name.lower() for entry in bans):
            bans.append({
                "uuid": p_uuid,
                "name": player_name,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S +0000"),
                "source": "Server",
                "expires": "forever",
                "reason": "Banned by an operator."
            })
            _write_json_file(ban_path, bans)
        return True, f"Banned player {player_name}"

    elif action == 'pardon':
        ban_path = os.path.join(server_path, 'banned-players.json')
        bans = _read_json_file(ban_path, [])
        bans = [entry for entry in bans if entry.get('name', '').lower() != player_name.lower()]
        _write_json_file(ban_path, bans)
        return True, f"Unbanned player {player_name}"

    return False, f"Unsupported action: {action}"

def execute_player_action(action, player_name, host='127.0.0.1', port=25575, password='', server_path='/wdc/PaperMC'):
    if not player_name:
        return False, "Player name is required"
        
    command_map = {
        'op': f"op {player_name}",
        'deop': f"deop {player_name}",
        'whitelist_add': f"whitelist add {player_name}",
        'whitelist_remove': f"whitelist remove {player_name}",
        'kick': f"kick {player_name}",
        'ban': f"ban {player_name}",
        'pardon': f"pardon {player_name}",
    }
    
    cmd = command_map.get(action)
    if not cmd:
        return False, f"Unknown action: {action}"
        
    # 1. If server is running, try sending RCON command
    is_running = get_service_status('papermc')
    if is_running:
        resp = send_rcon_command(cmd, host=host, port=port, password=password)
        if not resp.startswith("RCON Error"):
            return True, resp or "Command executed successfully"

    # 2. If server is offline (or RCON unreachable), modify JSON files directly
    if action == 'kick':
        return False, "Cannot kick player while server is offline"
        
    return _apply_player_action_offline(server_path, action, player_name)

# ============================================================
# File Manager Utilities
# ============================================================

def _safe_path(base_dir, relative_path):
    target = os.path.abspath(os.path.join(base_dir, relative_path.lstrip("/\\")))
    if not target.startswith(os.path.abspath(base_dir)):
        raise ValueError("Access outside server directory is denied.")
    return target

def list_server_files(server_path, relative_path=""):
    target_dir = _safe_path(server_path, relative_path)
    if not os.path.exists(target_dir):
        return []
    
    entries = []
    for item in sorted(os.listdir(target_dir)):
        item_path = os.path.join(target_dir, item)
        is_dir = os.path.isdir(item_path)
        size = 0 if is_dir else os.path.getsize(item_path)
        mtime = os.path.getmtime(item_path)
        
        entries.append({
            "name": item,
            "is_dir": is_dir,
            "size": size,
            "modified": datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M'),
            "relative_path": os.path.relpath(item_path, server_path)
        })
    # Sort folders first, then files
    return sorted(entries, key=lambda x: (not x['is_dir'], x['name'].lower()))

def read_server_file(server_path, relative_path):
    target = _safe_path(server_path, relative_path)
    if os.path.isdir(target):
        raise ValueError("Cannot read directory as text file.")
    with open(target, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def write_server_file(server_path, relative_path, content):
    target = _safe_path(server_path, relative_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'w', encoding='utf-8') as f:
        f.write(content)
    return True

def delete_server_item(server_path, relative_path):
    if not relative_path:
        raise ValueError("Cannot delete root server directory.")
    target = _safe_path(server_path, relative_path)
    if os.path.isdir(target):
        shutil.rmtree(target)
    else:
        os.remove(target)
    return True

def create_server_folder(server_path, relative_path):
    target = _safe_path(server_path, relative_path)
    os.makedirs(target, exist_ok=True)
    return True

# ============================================================
# Backup Manager Utilities
# ============================================================

def get_backups_dir(server_path):
    bdir = os.path.join(server_path, 'backups')
    os.makedirs(bdir, exist_ok=True)
    return bdir

def list_world_backups(server_path):
    bdir = get_backups_dir(server_path)
    backups = []
    for item in sorted(os.listdir(bdir), reverse=True):
        if item.endswith('.tar.gz') or item.endswith('.zip'):
            fpath = os.path.join(bdir, item)
            mtime = os.path.getmtime(fpath)
            backups.append({
                "filename": item,
                "size": os.path.getsize(fpath),
                "created": datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
    return backups

def create_world_backup(server_path, host='127.0.0.1', port=25575, password=''):
    # Run save-all via RCON if server is alive
    send_rcon_command("save-all", host=host, port=port, password=password)
    time.sleep(1)
    
    bdir = get_backups_dir(server_path)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    backup_name = f"world_backup_{timestamp}.tar.gz"
    backup_path = os.path.join(bdir, backup_name)
    
    world_folders = ['world', 'world_nether', 'world_the_end', 'server.properties', 'bukkit.yml', 'spigot.yml']
    
    try:
        with tarfile.open(backup_path, "w:gz") as tar:
            for item in world_folders:
                item_path = os.path.join(server_path, item)
                if os.path.exists(item_path):
                    tar.add(item_path, arcname=item)
        return True, backup_name
    except Exception as e:
        return False, str(e)

def restore_world_backup(server_path, backup_filename):
    bdir = get_backups_dir(server_path)
    backup_path = _safe_path(bdir, backup_filename)
    if not os.path.exists(backup_path):
        return False, "Backup file not found"
        
    # 1. Stop PaperMC
    control_service('papermc', 'stop')
    time.sleep(1)
    
    # 2. Remove current world folders
    for folder in ['world', 'world_nether', 'world_the_end']:
        fp = os.path.join(server_path, folder)
        if os.path.exists(fp):
            shutil.rmtree(fp, ignore_errors=True)
            
    # 3. Extract backup archive
    try:
        with tarfile.open(backup_path, "r:gz") as tar:
            tar.extractall(path=server_path)
        return True, "Backup restored successfully"
    except Exception as e:
        return False, str(e)

def delete_world_backup(server_path, backup_filename):
    bdir = get_backups_dir(server_path)
    backup_path = _safe_path(bdir, backup_filename)
    if os.path.exists(backup_path):
        os.remove(backup_path)
        return True, ""
    return False, "Backup file not found"

_last_net_time = 0
_last_net_bytes = (0, 0)
_cached_rate = {'upload_kbps': 0.0, 'download_kbps': 0.0}

def get_network_bandwidth():
    global _last_net_time, _last_net_bytes, _cached_rate
    now = time.time()
    try:
        counters = psutil.net_io_counters()
        cur_bytes = (counters.bytes_sent, counters.bytes_recv)
        if _last_net_time > 0:
            dt = max(now - _last_net_time, 0.1)
            up = ((cur_bytes[0] - _last_net_bytes[0]) / 1024.0) / dt
            down = ((cur_bytes[1] - _last_net_bytes[1]) / 1024.0) / dt
            _cached_rate = {
                'upload_kbps': max(round(up, 1), 0.0),
                'download_kbps': max(round(down, 1), 0.0)
            }
        _last_net_time = now
        _last_net_bytes = cur_bytes
    except Exception:
        pass
    return _cached_rate

_last_ping_time = 0
_cached_ping = None

def get_tunnel_ping(domain="jakarta-baghdad.tun.ply.gg"):
    global _last_ping_time, _cached_ping
    now = time.time()
    if now - _last_ping_time < 3.0 and _cached_ping is not None:
        return _cached_ping
    try:
        res = subprocess.run(['ping', '-c', '1', '-W', '1', domain], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            m = re.search(r'time=([\d\.]+)\s*ms', res.stdout)
            if m:
                _cached_ping = float(m.group(1))
                _last_ping_time = now
                return _cached_ping
    except Exception:
        pass
    return None

