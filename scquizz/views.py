import json
import uuid
import time
import io
import asyncio
from gtts import gTTS

from django.http import JsonResponse, HttpResponse, FileResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

from .models import Message, Poll
from .consumers import notify_update

# --- Server-Sent Events (SSE) Pub/Sub ---
_sse_subscribers = set()

def notify_sse_subscribers(event_data="UPDATE"):
    """Broadcast event data to all connected SSE clients."""
    for q in list(_sse_subscribers):
        try:
            q.put_nowait(event_data)
        except Exception:
            pass

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login

# --- HTML & Static Views ---
def get_app_base(request):
    path = request.path.rstrip('/')
    for suffix in ['/admin.html', '/admin', '/login.html', '/login', '/index.html']:
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    return path.rstrip('/')

def index_view(request):
    return render(request, 'client/index.html', {
        'app_base': get_app_base(request),
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
            
    return render(request, 'login/login.html', {
        'app_base': app_base,
        'next': next_url,
        'error_message': error_message,
        'user': request.user
    })

def admin_view(request):
    app_base = get_app_base(request)
    if not request.user.is_authenticated:
        return redirect(f'{app_base}/login?next={request.path}')
    return render(request, 'admin/admin.html', {
        'app_base': app_base,
        'user': request.user
    })

# --- Messages API ---
@csrf_exempt
def messages_view(request):
    if request.method == "GET":
        messages = Message.objects.all().order_by("ts")
        data = [
            {
                "id": m.id,
                "name": m.name,
                "text": m.text,
                "ts": m.ts,
                "answered": m.answered,
            }
            for m in messages
        ]
        return JsonResponse(data, safe=False)

    elif request.method == "POST":
        try:
            body = json.loads(request.body)
            name = body.get("name", "")
            text = body.get("text", "")
            msg_id = str(uuid.uuid4())
            ts = int(time.time() * 1000)

            msg = Message.objects.create(
                id=msg_id,
                name=name,
                text=text,
                ts=ts,
                answered=0
            )

            notify_update()
            return JsonResponse({
                "id": msg.id,
                "name": msg.name,
                "text": msg.text,
                "ts": msg.ts,
                "answered": msg.answered,
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@csrf_exempt
@require_http_methods(["POST"])
def answer_message(request, msg_id):
    Message.objects.filter(id=msg_id).update(answered=1)
    notify_update()
    return JsonResponse({"success": True})

@csrf_exempt
@require_http_methods(["DELETE"])
def delete_message(request, msg_id):
    Message.objects.filter(id=msg_id).delete()
    notify_update()
    return JsonResponse({"success": True})

def message_tts(request, msg_id):
    msg = Message.objects.filter(id=msg_id).first()
    if not msg:
        return JsonResponse({"error": "Message not found"}, status=404)
    
    try:
        tts = gTTS(text=msg.text, lang='th')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return HttpResponse(fp.read(), content_type="audio/mpeg")
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# --- Polls API ---
@csrf_exempt
def polls_view(request):
    if request.method == "GET":
        polls = Poll.objects.all()
        data = [
            {
                "id": p.id,
                "question": p.question,
                "options": p.options,
                "votes": p.votes,
                "active": p.active,
                "type": p.type or "standard",
                "scope": p.scope,
            }
            for p in polls
        ]
        return JsonResponse(data, safe=False)

    elif request.method == "POST":
        try:
            body = json.loads(request.body)
            question = body.get("question", "")
            options = body.get("options", [])
            poll_type = body.get("type", "standard")
            scope = body.get("scope", None)
            poll_id = str(uuid.uuid4())

            votes = {} if poll_type == "location" else [0] * len(options)

            poll = Poll.objects.create(
                id=poll_id,
                question=question,
                options=options,
                votes=votes,
                active=0,
                type=poll_type,
                scope=scope
            )

            notify_update()
            return JsonResponse({
                "success": True,
                "id": poll.id,
                "question": poll.question,
                "options": poll.options,
                "type": poll.type,
                "scope": poll.scope
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "Method not allowed"}, status=405)

def active_poll_view(request):
    poll = Poll.objects.filter(active=1).first()
    if not poll:
        return JsonResponse(None, safe=False)
    return JsonResponse({
        "id": poll.id,
        "question": poll.question,
        "options": poll.options,
        "votes": poll.votes,
        "active": poll.active,
        "type": poll.type or "standard",
        "scope": poll.scope
    })

@csrf_exempt
@require_http_methods(["POST"])
def activate_poll(request, poll_id):
    Poll.objects.update(active=0)
    Poll.objects.filter(id=poll_id).update(active=1)
    notify_update()
    return JsonResponse({"success": True})

@csrf_exempt
@require_http_methods(["POST"])
def deactivate_poll(request, poll_id):
    Poll.objects.filter(id=poll_id).update(active=0)
    notify_update()
    return JsonResponse({"success": True})

@csrf_exempt
@require_http_methods(["DELETE"])
def delete_poll(request, poll_id):
    Poll.objects.filter(id=poll_id).delete()
    notify_update()
    return JsonResponse({"success": True})

THAI_PROVINCES_ALIASES = {
    'กรุงเทพมหานคร': ['กรุงเทพ', 'กทม', 'กทม.', 'bangkok'],
    'นครราชสีมา': ['โคราช', 'นม'],
    'อุบลราชธานี': ['อุบล'],
    'อุดรธานี': ['อุดร'],
    'สุราษฎร์ธานี': ['สุราษ', 'สุราษฎร์', 'สุราษฏร์'],
    'นครศรีธรรมราช': ['คอน', 'นครศรี'],
    'พระนครศรีอยุธยา': ['อยุธยา'],
    'ประจวบคีรีขันธ์': ['ประจวบ'],
    'พังงา': ['พังงา'],
    'สงขลา': ['หาดใหญ่', 'สงขลา'],
    'ชลบุรี': ['พัทยา', 'ชลบุรี', 'บางแสน'],
    'เชียงราย': ['ชร'],
    'เชียงใหม่': ['ชม']
}

def standardize_location_name(loc):
    if not loc:
        return loc
    loc = str(loc).strip()
    clean = loc
    for prefix in ['จังหวัด', 'จ.', 'จ ']:
        if clean.startswith(prefix):
            clean = clean[len(prefix):].strip()
            break
    
    for official, aliases in THAI_PROVINCES_ALIASES.items():
        if clean == official or clean in aliases or (len(clean) >= 3 and official.startswith(clean)):
            return official
    return loc

@csrf_exempt
@require_http_methods(["POST"])
def vote_poll(request, poll_id):
    poll = Poll.objects.filter(id=poll_id).first()
    if not poll:
        return JsonResponse({"error": "Poll not found"}, status=404)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    poll_type = poll.type or "standard"
    votes = poll.votes

    if poll_type == "location":
        loc = body.get("location")
        if not loc:
            return JsonResponse({"error": "Location value is required"}, status=400)
        
        # Standardize location name to official naming
        loc = standardize_location_name(loc)

        if not isinstance(votes, dict):
            votes = {}
        votes[loc] = votes.get(loc, 0) + 1
    else:
        option_index = body.get("option_index")
        if option_index is None or not isinstance(votes, list) or option_index < 0 or option_index >= len(votes):
            return JsonResponse({"error": "Invalid option index"}, status=400)
        votes[option_index] += 1

    poll.votes = votes
    poll.save()

    notify_update()
    return JsonResponse({"success": True})

def ws_probe(request):
    response = JsonResponse({"detail": "WebSocket upgrade required"}, status=426)
    response["Upgrade"] = "websocket"
    return response

async def poll_events_sse(request):
    """Server-Sent Events (SSE) stream for real-time poll status & votes"""
    queue = asyncio.Queue()
    _sse_subscribers.add(queue)

    async def event_stream():
        try:
            yield "data: CONNECTED\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            _sse_subscribers.discard(queue)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
