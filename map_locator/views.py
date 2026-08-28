import json
import uuid
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login
from .models import LocationMarker

# --- Helper to resolve mount path prefix dynamically ---
def get_app_base(request):
    path = request.path.rstrip('/')
    for suffix in ['/admin.html', '/admin', '/login.html', '/login', '/index.html']:
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    return path.rstrip('/')

# --- Web Page Views ---
def index_view(request):
    return render(request, 'map_locator/index.html', {
        'app_base': get_app_base(request),
        'user': request.user
    })

def admin_view(request):
    app_base = get_app_base(request)
    if not request.user.is_authenticated:
        return redirect(f'{app_base}/login?next={request.path}')
    return render(request, 'map_locator/admin.html', {
        'app_base': app_base,
        'user': request.user
    })

def login_view(request):
    app_base = get_app_base(request)
    next_url = request.GET.get('next') or request.POST.get('next') or f'{app_base}/admin'
    
    if request.user.is_authenticated:
        return redirect(next_url)
        
    error_message = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        # Authenticate against central User database
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(next_url)
        else:
            error_message = 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'
            
    return render(request, 'map_locator/login.html', {
        'app_base': app_base,
        'next': next_url,
        'error_message': error_message,
        'user': request.user
    })

# --- Locations REST API ---
@csrf_exempt
def locations_api(request):
    if request.method == "GET":
        markers = LocationMarker.objects.all().order_by('-created_at')
        category_filter = request.GET.get('category')
        if category_filter:
            markers = markers.filter(category=category_filter)

        data = [
            {
                "id": str(m.id),
                "title": m.title,
                "category": m.category,
                "description": m.description,
                "latitude": m.latitude,
                "longitude": m.longitude,
                "address": m.address,
                "created_by": m.created_by,
                "created_at": m.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
            for m in markers
        ]
        return JsonResponse(data, safe=False)

    elif request.method == "POST":
        try:
            body = json.loads(request.body)
            is_sos = body.get("is_sos", False)
            category = body.get("category", "เหตุด่วน" if is_sos else "ทั่วไป").strip() or "ทั่วไป"
            
            title = body.get("title", "").strip()
            if not title:
                if is_sos or category == "เหตุด่วน":
                    title = "🚨 สัญญาณ SOS ฉุกเฉิน"
                else:
                    return JsonResponse({"error": "Title is required"}, status=400)
            
            lat = float(body.get("latitude"))
            lng = float(body.get("longitude"))
            description = body.get("description", "").strip()
            address = body.get("address", "").strip()
            
            sender_name = body.get("created_by", "").strip()
            if not sender_name:
                sender_name = "ผู้แจ้งเหตุ SOS" if (is_sos or category == "เหตุด่วน") else ("แอดมิน" if request.user.is_authenticated else "ผู้ใช้ทั่วไป")

            marker = LocationMarker.objects.create(
                id=str(uuid.uuid4()),
                title=title,
                category=category,
                description=description,
                latitude=lat,
                longitude=lng,
                address=address,
                created_by=sender_name
            )

            return JsonResponse({
                "success": True,
                "id": str(marker.id),
                "title": marker.title,
                "category": marker.category,
                "latitude": marker.latitude,
                "longitude": marker.longitude,
                "address": marker.address,
                "created_by": marker.created_by,
                "created_at": marker.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@csrf_exempt
@require_http_methods(["DELETE", "POST"])
def delete_location_api(request, loc_id):
    marker = LocationMarker.objects.filter(id=loc_id).first()
    if not marker:
        return JsonResponse({"error": "Location not found"}, status=404)
    marker.delete()
    return JsonResponse({"success": True})
