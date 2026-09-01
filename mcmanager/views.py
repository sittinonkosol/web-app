import os
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from core.permissions import require_app_access
from .models import ServerSetting
from .utils import (
    get_max_allowed_ram_mb,
    get_service_status,
    control_service,
    get_java_resource_usage,
    send_rcon_command,
    parse_server_properties,
    save_server_properties
)

@require_app_access('mcmanager', 'viewer')
def dashboard_view(request):
    settings = ServerSetting.get_settings()
    max_ram = get_max_allowed_ram_mb()
    return render(request, 'mcmanager/dashboard.html', {
        'max_ram': max_ram,
        'current_ram': settings.max_ram_mb
    })

@require_http_methods(["GET"])
@require_app_access('mcmanager', 'viewer')
def api_server_status(request):
    mc_status = get_service_status('papermc')
    playit_status = get_service_status('playit')
    usage = get_java_resource_usage()
    
    return JsonResponse({
        "papermc_running": mc_status,
        "playit_running": playit_status,
        "cpu_percent": usage['cpu_percent'],
        "ram_mb": usage['ram_mb']
    })

@csrf_exempt
@require_http_methods(["POST"])
@require_app_access('mcmanager', 'admin')
def api_server_action(request):
    try:
        data = json.loads(request.body)
        service = data.get('service') # 'papermc' or 'playit'
        action = data.get('action') # 'start', 'stop', 'restart'
        
        if service not in ['papermc', 'playit'] or action not in ['start', 'stop', 'restart']:
            return JsonResponse({"error": "Invalid service or action"}, status=400)
            
        success = control_service(service, action)
        return JsonResponse({"success": success})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_app_access('mcmanager', 'admin')
def api_server_config(request):
    settings = ServerSetting.get_settings()
    props_path = f"{settings.server_path}/server.properties"
    
    if request.method == "GET":
        props = parse_server_properties(props_path)
        return JsonResponse({
            "ram_mb": settings.max_ram_mb,
            "properties": props
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
            
            # Update properties
            if 'properties' in data:
                # Ensure RCON is enabled and password matches
                props = data['properties']
                props['enable-rcon'] = 'true'
                props['rcon.password'] = settings.rcon_password
                props['rcon.port'] = str(settings.rcon_port)
                save_server_properties(props_path, props)
                
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@require_app_access('mcmanager', 'admin')
def api_send_rcon(request):
    try:
        data = json.loads(request.body)
        command = data.get('command')
        if not command:
            return JsonResponse({"error": "No command provided"}, status=400)
            
        settings = ServerSetting.get_settings()
        response = send_rcon_command(
            command, 
            host='127.0.0.1', 
            port=settings.rcon_port, 
            password=settings.rcon_password
        )
        return JsonResponse({"response": response})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
