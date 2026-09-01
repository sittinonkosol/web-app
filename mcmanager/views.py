import os
import json
from django.shortcuts import render
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from core.permissions import require_app_access
from .models import ServerSetting
from .utils import (
    get_max_allowed_ram_mb,
    get_service_status,
    control_service,
    get_java_resource_usage,
    send_rcon_command,
    parse_server_properties,
    save_server_properties,
    reset_world,
    get_players_data,
    execute_player_action,
    list_server_files,
    read_server_file,
    write_server_file,
    delete_server_item,
    create_server_folder,
    list_world_backups,
    create_world_backup,
    restore_world_backup,
    delete_world_backup,
    _safe_path,
    get_backups_dir,
    get_network_bandwidth,
    get_tunnel_ping,
    query_minecraft_slp,
    get_player_entity_data,
)

@require_app_access('mcmanager', 'viewer')
def dashboard_view(request):
    settings = ServerSetting.get_settings()
    max_ram_mb = get_max_allowed_ram_mb()
    max_ram_gb = round(max_ram_mb / 1024, 1)
    if max_ram_gb.is_integer():
        max_ram_gb = int(max_ram_gb)
        
    current_ram_gb = round(settings.max_ram_mb / 1024, 1)
    if current_ram_gb.is_integer():
        current_ram_gb = int(current_ram_gb)
    
    role = getattr(request, 'user_app_role', 'viewer')
    
    return render(request, 'mcmanager/dashboard.html', {
        'role': role,
        'max_ram_gb': max_ram_gb,
        'current_ram_gb': current_ram_gb,
        'rcon_port': settings.rcon_port,
        'server_path': settings.server_path,
        'user': request.user
    })

# ============================================================
# Status & Control APIs
# ============================================================

@require_http_methods(["GET"])
@require_app_access('mcmanager', 'viewer')
def api_server_status(request):
    settings = ServerSetting.get_settings()
    mc_status = get_service_status('papermc')
    playit_status = get_service_status('playit')
    usage = get_java_resource_usage()
    ping_ms = get_tunnel_ping("jakarta-baghdad.tun.ply.gg") if playit_status else None
    net_stats = get_network_bandwidth()
    
    slp_data = query_minecraft_slp(port=25565) if mc_status else {}
    is_ready = bool(slp_data and 'version' in slp_data)
    players_info = slp_data.get('players', {})
    
    if not mc_status:
        server_state = "offline"
    elif not is_ready:
        server_state = "init"
    else:
        server_state = "online"
    
    return JsonResponse({
        "papermc_running": mc_status,
        "papermc_ready": is_ready,
        "server_state": server_state,
        "playit_running": playit_status,
        "playit_domain": "jakarta-baghdad.tun.ply.gg",
        "ping_ms": ping_ms,
        "upload_kbps": net_stats['upload_kbps'],
        "download_kbps": net_stats['download_kbps'],
        "cpu_percent": usage['cpu_percent'],
        "ram_mb": usage['ram_mb'],
        "uptime": usage.get('uptime', 'Offline'),
        "players_online": players_info.get('online', 0),
        "players_max": players_info.get('max', 20)
    })

@csrf_exempt
@require_http_methods(["POST"])
@require_app_access('mcmanager', 'admin')
def api_server_action(request):
    try:
        data = json.loads(request.body)
        service = data.get('service') # 'papermc' or 'playit'
        action = data.get('action') # 'start', 'stop', 'restart', 'reset_world'
        
        if action == 'reset_world':
            settings = ServerSetting.get_settings()
            success, err_msg = reset_world(settings.server_path)
            if success:
                return JsonResponse({"success": True})
            return JsonResponse({"success": False, "error": err_msg})
            
        if service not in ['papermc', 'playit'] or action not in ['start', 'stop', 'restart']:
            return JsonResponse({"error": "Invalid service or action"}, status=400)
            
        success, err_msg = control_service(service, action)
        if success:
            try:
                from .consumers import ConsoleConsumer
                import asyncio
                username = getattr(request.user, 'username', 'Admin')
                loop = asyncio.get_event_loop()
                if loop.is_running() and service == 'papermc':
                    asyncio.create_task(ConsoleConsumer.broadcast({
                        "type": "console_message",
                        "message": f"\x1b[33m[Server Control] Action '{action.upper()}' performed by {username}\x1b[0m\n",
                    }))
            except Exception:
                pass
            return JsonResponse({"success": True})
        else:
            return JsonResponse({"success": False, "error": err_msg})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

PROTECTED_PROPERTIES = {
    'enable-rcon', 'rcon.password', 'rcon.port', 'rcon.ip',
    'server-ip', 'server-port', 'query.port', 'enable-query',
    'network-compression-threshold', 'prevent-proxy-connections',
    'management-server-allowed-origins', 'management-server-enabled',
    'management-server-host', 'management-server-port', 'management-server-secret',
    'management-server-tls-enabled', 'management-server-tls-keystore', 'management-server-tls-keystore-password'
}

@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_app_access('mcmanager', 'admin')
def api_server_config(request):
    settings = ServerSetting.get_settings()
    props_path = f"{settings.server_path}/server.properties"
    
    if request.method == "GET":
        raw_props = parse_server_properties(props_path)
        # Filter out sensitive / connection locking properties
        safe_props = {k: v for k, v in raw_props.items() if k not in PROTECTED_PROPERTIES and not k.startswith('rcon.') and not k.startswith('management-server')}
        return JsonResponse({
            "ram_mb": settings.max_ram_mb,
            "properties": safe_props
        })
    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            # Update RAM
            if 'ram_mb' in data:
                ram = int(data['ram_mb'])
                max_ram = get_max_allowed_ram_mb()
                if ram > max_ram:
                    ram = max_ram
                settings.max_ram_mb = ram
                settings.save()
                
                # Rewrite start.sh
                start_sh_path = f"{settings.server_path}/start.sh"
                try:
                    with open(start_sh_path, 'w', encoding='utf-8') as f:
                        f.write(f"#!/bin/bash\njava -Xms1024M -Xmx{ram}M -jar paper.jar --nogui\n")
                    os.chmod(start_sh_path, 0o755)
                except Exception as e:
                    print("Failed to rewrite start.sh:", e)
            
            # Update properties safely preserving vital infrastructure
            if 'properties' in data:
                original_props = parse_server_properties(props_path)
                submitted_props = data['properties']
                
                # Merge safe submitted properties over original properties
                for k, v in submitted_props.items():
                    if k not in PROTECTED_PROPERTIES and not k.startswith('rcon.') and not k.startswith('management-server'):
                        original_props[k] = str(v)
                        
                # Re-assert vital connection & RCON parameters
                original_props['enable-rcon'] = 'true'
                original_props['rcon.password'] = settings.rcon_password
                original_props['rcon.port'] = str(settings.rcon_port)
                original_props['server-port'] = '25565'
                original_props['server-ip'] = ''
                
                save_server_properties(props_path, original_props)
                
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@require_app_access('mcmanager', 'admin')
def api_send_rcon(request):
    try:
        data = json.loads(request.body)
        cmd = data.get('command')
        if not cmd:
            return JsonResponse({"error": "Command is required"}, status=400)
            
        settings = ServerSetting.get_settings()
        response = send_rcon_command(cmd, port=settings.rcon_port, password=settings.rcon_password)

        try:
            from .consumers import ConsoleConsumer
            import asyncio
            username = getattr(request.user, 'username', 'Web')
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(ConsoleConsumer.broadcast({
                    "type": "console_message",
                    "message": f"\x1b[32m> \x1b[1m{cmd}\x1b[0m \x1b[90m(by {username})\x1b[0m\n",
                    "is_command": True,
                    "command": cmd
                }))
                if response:
                    resp_lines = response.strip().split('\n')
                    formatted_resp = '\n'.join(f"\x1b[37m< {line}\x1b[0m" for line in resp_lines) + '\n'
                    asyncio.create_task(ConsoleConsumer.broadcast({
                        "type": "console_message",
                        "message": formatted_resp,
                        "is_response": True
                    }))
        except Exception:
            pass

        return JsonResponse({"response": response})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# ============================================================
# Players API
# ============================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_app_access('mcmanager', 'admin')
def api_players(request):
    settings = ServerSetting.get_settings()
    if request.method == "GET":
        data = get_players_data(settings.server_path, port=settings.rcon_port, password=settings.rcon_password)
        return JsonResponse(data)
    elif request.method == "POST":
        try:
            body = json.loads(request.body)
            action = body.get('action')
            player_name = body.get('player_name')
            success, msg = execute_player_action(
                action, 
                player_name, 
                port=settings.rcon_port, 
                password=settings.rcon_password, 
                server_path=settings.server_path
            )
            if success:
                return JsonResponse({"success": True, "message": msg})
            return JsonResponse({"success": False, "error": msg}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

@require_http_methods(["GET"])
@require_app_access('mcmanager', 'viewer')
def api_player_entity_data(request):
    try:
        player_name = request.GET.get('player', '').strip()
        if not player_name:
            return JsonResponse({"success": False, "error": "Player name parameter is required"})
        
        settings = ServerSetting.get_settings()
        data = get_player_entity_data(
            player_name, 
            host='127.0.0.1', 
            port=settings.rcon_port, 
            password=settings.rcon_password, 
            server_path=settings.server_path
        )
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Entity fetch error: {str(e)}"})

ITEM_ICONS_DIR = os.path.join(os.path.dirname(__file__), 'templates', 'mcmanager', 'Minecraft_Item')

@require_http_methods(["GET"])
def api_item_icon(request, item_name):
    """Serve Minecraft item PNG icons dynamically."""
    from django.http import FileResponse, Http404
    clean_name = item_name.replace('minecraft:', '').strip().lower()
    if clean_name.endswith('.png'):
        clean_name = clean_name[:-4]
    
    file_path = os.path.join(ITEM_ICONS_DIR, f"{clean_name}.png")
    if os.path.isfile(file_path):
        return FileResponse(open(file_path, 'rb'), content_type='image/png')
    
    # Fallback to barrier if not found
    fallback_path = os.path.join(ITEM_ICONS_DIR, 'barrier.png')
    if os.path.isfile(fallback_path):
        return FileResponse(open(fallback_path, 'rb'), content_type='image/png')
    raise Http404("Item icon not found")

# ============================================================
# File Manager API
# ============================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_app_access('mcmanager', 'admin')
def api_files(request):
    settings = ServerSetting.get_settings()
    if request.method == "GET":
        path = request.GET.get('path', '')
        mode = request.GET.get('mode', 'list') # 'list' or 'read'
        
        try:
            if mode == 'read':
                content = read_server_file(settings.server_path, path)
                return JsonResponse({"content": content, "path": path})
            else:
                files = list_server_files(settings.server_path, path)
                return JsonResponse({"files": files, "current_path": path})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
            
    elif request.method == "POST":
        try:
            # 1. File Upload (multipart/form-data)
            if 'file' in request.FILES:
                uploaded_file = request.FILES['file']
                rel_dir = request.POST.get('path', '')
                target_dir = _safe_path(settings.server_path, rel_dir)
                dest_path = os.path.join(target_dir, uploaded_file.name)
                
                with open(dest_path, 'wb+') as dest:
                    for chunk in uploaded_file.chunks():
                        dest.write(chunk)
                return JsonResponse({"success": True, "filename": uploaded_file.name})

            # 2. JSON actions (save, delete, mkdir)
            data = {}
            if request.content_type == 'application/json' and request.body:
                try:
                    data = json.loads(request.body)
                except Exception:
                    data = {}
            else:
                data = request.POST

            action = data.get('action')
            path = data.get('path')

            if action == 'save':
                content = data.get('content', '')
                write_server_file(settings.server_path, path, content)
                return JsonResponse({"success": True})
                
            elif action == 'delete':
                delete_server_item(settings.server_path, path)
                return JsonResponse({"success": True})
                
            elif action == 'mkdir':
                create_server_folder(settings.server_path, path)
                return JsonResponse({"success": True})
                
            return JsonResponse({"error": "Unknown file action"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

# ============================================================
# Backups API
# ============================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_app_access('mcmanager', 'admin')
def api_backups(request):
    settings = ServerSetting.get_settings()
    if request.method == "GET":
        backups = list_world_backups(settings.server_path)
        return JsonResponse({"backups": backups})
    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            action = data.get('action')
            
            if action == 'create':
                success, result = create_world_backup(settings.server_path, port=settings.rcon_port, password=settings.rcon_password)
                if success:
                    return JsonResponse({"success": True, "filename": result})
                return JsonResponse({"success": False, "error": result}, status=500)
                
            elif action == 'restore':
                filename = data.get('filename')
                success, result = restore_world_backup(settings.server_path, filename)
                if success:
                    return JsonResponse({"success": True, "message": result})
                return JsonResponse({"success": False, "error": result}, status=500)
                
            elif action == 'delete':
                filename = data.get('filename')
                success, result = delete_world_backup(settings.server_path, filename)
                if success:
                    return JsonResponse({"success": True})
                return JsonResponse({"success": False, "error": result}, status=400)
                
            return JsonResponse({"error": "Unknown backup action"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

@require_http_methods(["GET"])
@require_app_access('mcmanager', 'admin')
def api_download_backup(request, filename):
    settings = ServerSetting.get_settings()
    bdir = get_backups_dir(settings.server_path)
    try:
        fpath = _safe_path(bdir, filename)
        if not os.path.exists(fpath):
            raise Http404("Backup file not found")
        return FileResponse(open(fpath, 'rb'), as_attachment=True, filename=filename)
    except Exception:
        raise Http404("Invalid backup path")

@require_http_methods(["GET"])
@require_app_access('mcmanager', 'admin')
def api_download_log(request):
    settings = ServerSetting.get_settings()
    log_path = os.path.join(settings.server_path, 'logs', 'latest.log')
    if not os.path.exists(log_path):
        raise Http404("Log file not found")
    return FileResponse(open(log_path, 'rb'), as_attachment=True, filename='latest.log')

@csrf_exempt
@require_http_methods(["POST"])
@require_app_access('mcmanager', 'admin')
def api_clear_log(request):
    settings = ServerSetting.get_settings()
    log_path = os.path.join(settings.server_path, 'logs', 'latest.log')
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.truncate(0)
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
