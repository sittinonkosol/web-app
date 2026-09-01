import os
import psutil
import subprocess
from mcrcon import MCRcon

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
        result = subprocess.run(['sudo', 'systemctl', 'is-active', service_name], capture_output=True, text=True)
        return result.stdout.strip() == 'active'
    except Exception:
        return False

def control_service(service_name, action):
    if action not in ['start', 'stop', 'restart']:
        return False
    try:
        subprocess.run(['sudo', 'systemctl', action, service_name], check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def get_java_resource_usage():
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'java' in proc.info['name'].lower() and proc.info['cmdline'] and 'paper' in ' '.join(proc.info['cmdline']).lower():
                cpu = proc.cpu_percent(interval=0.1)
                mem = proc.memory_info().rss / (1024 * 1024)
                return {"cpu_percent": cpu, "ram_mb": mem}
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return {"cpu_percent": 0.0, "ram_mb": 0.0}

def send_rcon_command(command, host='127.0.0.1', port=25575, password=''):
    if not password:
        return "Error: RCON password not configured."
    try:
        with MCRcon(host, password, port=port) as mcr:
            resp = mcr.command(command)
            return resp
    except Exception as e:
        return f"RCON Error: {str(e)}"
