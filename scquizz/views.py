import json
import uuid
import time
import io
import asyncio
import logging
from gtts import gTTS
from tnprofanity.tnprofanity import Profane

from django.http import JsonResponse, HttpResponse, FileResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.core.paginator import Paginator
from django.core.cache import cache
from scquizz.models import Message, Poll, QuizSession
from scquizz.middleware import get_real_ip

from .models import Message, Poll, QuizSession
from .consumers import notify_update

logger = logging.getLogger('scquizz')

# --- Profanity Filter ---
EXTRA_BLACKLIST = [
    'fuck', 'shit', 'bitch', 'asshole', 'dick', 'pussy', 'bastard', 'cunt', 'bullshit',
    'เย็ด', 'เหี้ย', 'สัส', 'ควย', 'มึง', 'กู', 'ห่า', 'ดอกทอง', 'ระยำ', 'จัญไร', 'ชาติหมา'
]

def check_profanity(text):
    if not text:
        return False
    try:
        res = Profane.check(str(text), blacklist=EXTRA_BLACKLIST)
        return len(res) > 0
    except Exception:
        lower = str(text).lower()
        return any(w in lower for w in EXTRA_BLACKLIST)

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

from core.permissions import require_app_access, has_app_permission, get_user_app_role

# --- Session Helpers ---
def get_active_session(session_id=None):
    if session_id:
        sess = QuizSession.objects.filter(id=session_id).first()
        if sess:
            return sess
    sess = QuizSession.objects.filter(is_active=True).first()
    if sess:
        return sess
    return QuizSession.objects.first()

# --- HTML & Static Views ---
def get_app_base(request):
    path = request.path.rstrip('/')
    for suffix in ['/admin.html', '/admin', '/login.html', '/login', '/index.html']:
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    return path.rstrip('/')

@require_app_access('scquizz', min_role='viewer')
def index_view(request):
    session_id = request.GET.get('session')
    session = get_active_session(session_id)
    return render(request, 'client/index.html', {
        'app_base': get_app_base(request),
        'user': request.user,
        'current_session': session
    })

def login_view(request):
    app_base = get_app_base(request)
    raw_next = request.POST.get('next') or request.GET.get('next') or f'{app_base}/admin'
    from core.views import sanitize_next_url
    next_url = sanitize_next_url(raw_next)

    if request.user.is_authenticated:
        return redirect(next_url)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active:
            login(request, user)
            return redirect(next_url)

    return redirect(f'/login/?next={next_url}')

def admin_view(request):
    app_base = get_app_base(request)
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    
    if not has_app_permission(request.user, 'scquizz', min_role='moderator'):
        return render(request, 'core/permission_denied.html', {
            'app_name': 'scquizz',
            'display_name': 'SC Quiz (Admin Panel)',
            'required_role': 'moderator',
            'user_role': get_user_app_role(request.user, 'scquizz'),
            'user': request.user
        }, status=403)

    sessions = QuizSession.objects.all().order_by("-created_at")
    return render(request, 'admin/admin.html', {
        'app_base': app_base,
        'user': request.user,
        'sessions': sessions
    })

def sanitize_text(val, max_len=1000):
    if val is None:
        return ""
    val = str(val).replace('\x00', '').strip()
    return val[:max_len]

# --- Permission helper for scquizz APIs ---
def _require_moderator(request):
    """
    Returns a JsonResponse error if the request user is not authenticated
    or does not have moderator+ access on 'scquizz'. Returns None if OK.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'กรุณาเข้าสู่ระบบก่อนทำรายการ'}, status=401)
    if not has_app_permission(request.user, 'scquizz', min_role='moderator'):
        return JsonResponse({'error': 'ไม่มีสิทธิ์เข้าถึง ต้องการสิทธิ์ moderator ขึ้นไป'}, status=403)
    return None

# --- Sessions API ---
@csrf_exempt
def sessions_view(request):
    # Both GET and POST require moderator access
    auth_err = _require_moderator(request)
    if auth_err:
        return auth_err

    if request.method == "GET":
        sessions = QuizSession.objects.all().order_by("-created_at")
        data = [
            {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "is_active": s.is_active,
                "created_at": s.created_at.strftime('%Y-%m-%d %H:%M'),
                "messages_count": s.messages.count(),
                "polls_count": s.polls.count(),
                "rate_limit_per_minute": s.rate_limit_per_minute,
                "cooldown_seconds": s.cooldown_seconds,
            }
            for s in sessions
        ]
        return JsonResponse(data, safe=False)

    elif request.method == "POST":
        try:
            body = json.loads(request.body)
            title = sanitize_text(body.get("title", ""), max_len=200)
            if not title:
                return JsonResponse({"error": "กรุณาระบุชื่อ Session"}, status=400)
            desc = sanitize_text(body.get("description", ""), max_len=1000)
            is_active = bool(body.get("is_active", False))

            session_id = f"session_{uuid.uuid4().hex[:8]}"
            if is_active:
                QuizSession.objects.update(is_active=False)

            sess = QuizSession.objects.create(
                id=session_id,
                title=title,
                description=desc,
                is_active=is_active or not QuizSession.objects.filter(is_active=True).exists()
            )
            logger.info(f"Session created: {sess.id!r} title={sess.title!r} by user={request.user.username!r}")
            notify_update()
            return JsonResponse({
                "success": True,
                "id": sess.id,
                "title": sess.title,
                "description": sess.description,
                "is_active": sess.is_active,
                "created_at": sess.created_at.strftime('%Y-%m-%d %H:%M'),
                "messages_count": 0,
                "polls_count": 0,
                "rate_limit_per_minute": sess.rate_limit_per_minute,
                "cooldown_seconds": sess.cooldown_seconds,
            })
        except Exception as e:
            logger.error(f"sessions_view POST error: {e}", exc_info=True)
            return JsonResponse({"error": "เกิดข้อผิดพลาด กรุณาลองอีกครั้ง"}, status=400)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@csrf_exempt
@require_http_methods(["PATCH"])
def update_session_settings(request, session_id):
    """อัปเดตการตั้งค่า Rate Limit และ Cooldown ของ Session"""
    auth_err = _require_moderator(request)
    if auth_err:
        return auth_err
    sess = QuizSession.objects.filter(id=session_id).first()
    if not sess:
        return JsonResponse({"error": "Session not found"}, status=404)
    try:
        body = json.loads(request.body)
        if 'rate_limit_per_minute' in body:
            val = int(body['rate_limit_per_minute'])
            sess.rate_limit_per_minute = max(0, val)
        if 'cooldown_seconds' in body:
            val = int(body['cooldown_seconds'])
            sess.cooldown_seconds = max(0, val)
        sess.save()
        logger.info(f"Session settings updated: {sess.id!r} rate={sess.rate_limit_per_minute}/min cooldown={sess.cooldown_seconds}s by user={request.user.username!r}")
        return JsonResponse({
            "success": True,
            "rate_limit_per_minute": sess.rate_limit_per_minute,
            "cooldown_seconds": sess.cooldown_seconds,
        })
    except Exception as e:
        logger.error(f"update_session_settings error session={session_id}: {e}", exc_info=True)
        return JsonResponse({"error": "เกิดข้อผิดพลาด กรุณาลองอีกครั้ง"}, status=400)

@csrf_exempt
@require_http_methods(["POST"])
def activate_session(request, session_id):
    auth_err = _require_moderator(request)
    if auth_err:
        return auth_err
    sess = QuizSession.objects.filter(id=session_id).first()
    if not sess:
        return JsonResponse({"error": "Session not found"}, status=404)
    QuizSession.objects.update(is_active=False)
    sess.is_active = True
    sess.save()
    notify_update()
    return JsonResponse({"success": True, "active_id": sess.id, "active_title": sess.title})

@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
def session_detail_view(request, session_id):
    auth_err = _require_moderator(request)
    if auth_err:
        return auth_err
    sess = QuizSession.objects.filter(id=session_id).first()
    if not sess:
        return JsonResponse({"error": "Session not found"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": sess.id,
            "title": sess.title,
            "description": sess.description,
            "is_active": sess.is_active,
            "created_at": sess.created_at.strftime('%Y-%m-%d %H:%M'),
            "messages_count": sess.messages.count(),
            "polls_count": sess.polls.count(),
            "rate_limit_per_minute": sess.rate_limit_per_minute,
            "cooldown_seconds": sess.cooldown_seconds,
        })

    elif request.method in ["PUT", "PATCH"]:
        try:
            body = json.loads(request.body)
            if "title" in body:
                title = sanitize_text(body.get("title", ""), max_len=200)
                if not title:
                    return JsonResponse({"error": "กรุณาระบุชื่อ Session"}, status=400)
                sess.title = title

            if "description" in body:
                sess.description = sanitize_text(body.get("description", ""), max_len=1000)

            if "is_active" in body:
                is_active = bool(body.get("is_active"))
                if is_active and not sess.is_active:
                    QuizSession.objects.exclude(id=sess.id).update(is_active=False)
                    sess.is_active = True
                elif not is_active and sess.is_active:
                    sess.is_active = False

            if "rate_limit_per_minute" in body:
                val = int(body["rate_limit_per_minute"])
                sess.rate_limit_per_minute = max(0, val)

            if "cooldown_seconds" in body:
                val = int(body["cooldown_seconds"])
                sess.cooldown_seconds = max(0, val)

            sess.save()
            logger.info(f"Session updated: {sess.id!r} title={sess.title!r} by user={request.user.username!r}")
            notify_update()

            return JsonResponse({
                "success": True,
                "id": sess.id,
                "title": sess.title,
                "description": sess.description,
                "is_active": sess.is_active,
                "created_at": sess.created_at.strftime('%Y-%m-%d %H:%M'),
                "messages_count": sess.messages.count(),
                "polls_count": sess.polls.count(),
                "rate_limit_per_minute": sess.rate_limit_per_minute,
                "cooldown_seconds": sess.cooldown_seconds,
            })
        except Exception as e:
            logger.error(f"session_detail_view PUT error session={session_id}: {e}", exc_info=True)
            return JsonResponse({"error": "เกิดข้อผิดพลาด กรุณาลองอีกครั้ง"}, status=400)

    elif request.method == "DELETE":
        was_active = sess.is_active
        logger.info(f"Session deleted: {sess.id!r} title={sess.title!r} by user={request.user.username!r}")
        sess.delete()
        if was_active:
            remaining = QuizSession.objects.first()
            if remaining:
                remaining.is_active = True
                remaining.save()
        notify_update()
        return JsonResponse({"success": True})

delete_session = session_detail_view

# --- Messages API ---
@csrf_exempt
def messages_view(request):
    if request.method == "GET":
        # GET requires at least viewer access to protect student messages
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'กรุณาเข้าสู่ระบบก่อน'}, status=401)

        session_id = request.GET.get("session_id")
        session = get_active_session(session_id)
        if not session:
            return JsonResponse([], safe=False)

        # Pagination: ?limit=50&offset=0
        try:
            limit = min(int(request.GET.get("limit", 50)), 200)
            offset = max(int(request.GET.get("offset", 0)), 0)
        except (ValueError, TypeError):
            limit, offset = 50, 0

        messages_qs = Message.objects.filter(session=session).order_by("ts")
        total = messages_qs.count()
        messages = messages_qs[offset:offset + limit]
        data = [
            {
                "id": m.id,
                "name": m.name,
                "text": m.text,
                "ts": m.ts,
                "answered": m.answered,
                "session_id": m.session_id,
            }
            for m in messages
        ]
        resp = JsonResponse(data, safe=False)
        resp['X-Total-Count'] = str(total)
        return resp

    elif request.method == "POST":
        try:
            body = json.loads(request.body)
            session_id = body.get("session_id") or request.GET.get("session_id")
            session = get_active_session(session_id)
            if not session:
                return JsonResponse({"error": "ไม่มี Session ที่เปิดใช้งานอยู่ในขณะนี้"}, status=400)

            name = sanitize_text(body.get("name", ""), max_len=60)
            if not name:
                name = 'ไม่บอกชื่อ'
            text = sanitize_text(body.get("text", ""), max_len=1000)
            if not text:
                return JsonResponse({"error": "ข้อความต้องไม่ว่างเปล่า"}, status=400)

            # Profanity Filter
            if check_profanity(name) or check_profanity(text):
                logger.warning(f"Profanity blocked: name={name[:30]!r}")
                return JsonResponse({"error": "ข้อความมีเนื้อหาที่ไม่เหมาะสม กรุณาแก้ไขก่อนส่ง"}, status=400)

            msg_id = str(uuid.uuid4())
            ts = int(time.time() * 1000)

            msg = Message.objects.create(
                id=msg_id,
                session=session,
                name=name,
                text=text,
                ts=ts,
                answered=0
            )

            logger.info(f"Message posted: session={session.id!r} name={name!r}")
            notify_update()

            # Set backend Rate Limit Cooldown for this IP
            if session.cooldown_seconds > 0:
                ip = get_real_ip(request)
                cooldown_key = f'ratelimit:cooldown:{ip}'
                cache.set(cooldown_key, time.time() + session.cooldown_seconds, timeout=session.cooldown_seconds)

            resp = JsonResponse({
                "id": msg.id,
                "name": msg.name,
                "text": msg.text,
                "ts": msg.ts,
                "answered": msg.answered,
                "session_id": session.id,
                "cooldown_seconds": session.cooldown_seconds,
            })
            resp['X-Cooldown-Seconds'] = str(session.cooldown_seconds)
            return resp
        except Exception as e:
            logger.error(f"messages_view POST error: {e}", exc_info=True)
            return JsonResponse({"error": "เกิดข้อผิดพลาด กรุณาลองอีกครั้ง"}, status=400)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@csrf_exempt
@require_http_methods(["POST"])
def answer_message(request, msg_id):
    auth_err = _require_moderator(request)
    if auth_err:
        return auth_err
    Message.objects.filter(id=msg_id).update(answered=1)
    notify_update()
    return JsonResponse({"success": True})

@csrf_exempt
@require_http_methods(["DELETE"])
def delete_message(request, msg_id):
    auth_err = _require_moderator(request)
    if auth_err:
        return auth_err
    Message.objects.filter(id=msg_id).delete()
    notify_update()
    return JsonResponse({"success": True})

def message_tts(request, msg_id):
    msg = Message.objects.filter(id=msg_id).first()
    if not msg:
        return JsonResponse({"error": "Message not found"}, status=404)
    
    try:
        # Limit TTS input length to avoid overload
        tts_text = sanitize_text(msg.text, max_len=500)
        tts = gTTS(text=tts_text, lang='th')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return HttpResponse(fp.read(), content_type="audio/mpeg")
    except Exception as e:
        logger.error(f"message_tts error msg={msg_id}: {e}", exc_info=True)
        return JsonResponse({"error": "ไม่สามารถสร้างเสียงได้ กรุณาลองอีกครั้ง"}, status=500)

# --- Polls API ---
@csrf_exempt
def polls_view(request):
    session_id = request.GET.get("session_id")
    session = get_active_session(session_id)

    if request.method == "GET":
        # Public GET — clients need to see polls without login
        if not session:
            return JsonResponse([], safe=False)
        polls = Poll.objects.filter(session=session)
        data = [
            {
                "id": p.id,
                "question": p.question,
                "options": p.options,
                "votes": p.votes,
                "active": p.active,
                "type": p.type or "standard",
                "scope": p.scope,
                "session_id": p.session_id,
            }
            for p in polls
        ]
        return JsonResponse(data, safe=False)

    elif request.method == "POST":
        # Creating polls requires moderator access
        auth_err = _require_moderator(request)
        if auth_err:
            return auth_err
        try:
            body = json.loads(request.body)
            question = sanitize_text(body.get("question", ""), max_len=500)
            if not question:
                return JsonResponse({"error": "กรุณาป้อนคำถาม"}, status=400)

            if not session:
                session = QuizSession.objects.create(title="General Session", is_active=True)

            poll_type = body.get("type", "standard")
            if poll_type not in ["standard", "location"]:
                poll_type = "standard"

            raw_options = body.get("options", [])
            options = []
            if isinstance(raw_options, list):
                for opt in raw_options:
                    opt_str = sanitize_text(opt, max_len=200)
                    if opt_str:
                        options.append(opt_str)

            if poll_type == "standard" and len(options) < 2:
                return JsonResponse({"error": "กรุณาป้อนตัวเลือกอย่างน้อย 2 ตัวเลือก"}, status=400)

            scope = body.get("scope", "")
            if scope and isinstance(scope, str):
                scope = sanitize_text(scope, max_len=100)
            else:
                scope = ""

            poll_id = str(uuid.uuid4())
            votes = {} if poll_type == "location" else [0] * len(options)

            poll = Poll.objects.create(
                id=poll_id,
                session=session,
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
                "scope": poll.scope,
                "session_id": session.id,
            })
        except Exception as e:
            logger.error(f"polls_view POST error: {e}", exc_info=True)
            return JsonResponse({"error": "เกิดข้อผิดพลาด กรุณาลองอีกครั้ง"}, status=400)

    return JsonResponse({"error": "Method not allowed"}, status=405)

def active_poll_view(request):
    session_id = request.GET.get("session_id")
    session = get_active_session(session_id)
    if not session:
        return JsonResponse(None, safe=False)
    poll = Poll.objects.filter(session=session, active=1).first()
    if not poll:
        return JsonResponse(None, safe=False)
    return JsonResponse({
        "id": poll.id,
        "question": poll.question,
        "options": poll.options,
        "votes": poll.votes,
        "active": poll.active,
        "type": poll.type or "standard",
        "scope": poll.scope,
        "session_id": poll.session_id,
    })

@csrf_exempt
@require_http_methods(["POST"])
def activate_poll(request, poll_id):
    auth_err = _require_moderator(request)
    if auth_err:
        return auth_err
    poll = Poll.objects.filter(id=poll_id).first()
    if not poll:
        return JsonResponse({"error": "Poll not found"}, status=404)
    # Deactivate other polls in this same session
    Poll.objects.filter(session=poll.session).update(active=0)
    poll.active = 1
    poll.save()
    notify_update()
    return JsonResponse({"success": True})

@csrf_exempt
@require_http_methods(["POST"])
def deactivate_poll(request, poll_id):
    auth_err = _require_moderator(request)
    if auth_err:
        return auth_err
    Poll.objects.filter(id=poll_id).update(active=0)
    notify_update()
    return JsonResponse({"success": True})

@csrf_exempt
@require_http_methods(["DELETE"])
def delete_poll(request, poll_id):
    auth_err = _require_moderator(request)
    if auth_err:
        return auth_err
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
        loc = sanitize_text(body.get("location"), max_len=100)
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
