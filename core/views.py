import json
import logging
from functools import wraps
from urllib.parse import urlparse
from django.apps import apps
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import get_resolver, URLResolver
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction

logger = logging.getLogger('core')


def robots_txt(request):
    """Serve robots.txt blocking all web search crawlers and AI scrapers."""
    content = """User-agent: *
Disallow: /

# AI Training Crawlers
User-agent: GPTBot
Disallow: /

User-agent: ChatGPT-User
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: PerplexityBot
Disallow: /

User-agent: Bytespider
Disallow: /

User-agent: Amazonbot
Disallow: /

User-agent: Diffbot
Disallow: /

User-agent: FacebookBot
Disallow: /

User-agent: cohere-ai
Disallow: /

User-agent: YouBot
Disallow: /

User-agent: DataForSeoBot
Disallow: /

User-agent: PetalBot
Disallow: /

User-agent: SemrushBot
Disallow: /

User-agent: AhrefsBot
Disallow: /
"""
    return HttpResponse(content, content_type='text/plain')


from .models import AppSetting, UserAppPermission, GroupAppPermission, UserLoginLog
from .permissions import (
    get_app_setting,
    get_user_app_role,
    has_app_permission,
    is_app_public,
    ROLE_LEVELS
)

def get_installed_user_apps():
    """Discover all non-system installed apps that have routes."""
    user_apps = []
    exclude_apps = [
        'admin', 'auth', 'contenttypes', 'sessions', 'messages', 'staticfiles',
        'daphne', 'channels', 'core'
    ]
    for app_config in apps.get_app_configs():
        if app_config.name not in exclude_apps:
            dynamic_url = get_mounted_app_url(app_config.name)
            if dynamic_url:
                setting = get_app_setting(app_config.name)
                default_name = getattr(app_config, 'verbose_name', app_config.name.replace('_', ' ').title())
                default_icon = getattr(app_config, 'landing_icon', '🚀')
                default_desc = getattr(app_config, 'landing_description', f'Explore the {default_name} application.')
                user_apps.append({
                    'app_name': app_config.name,
                    'name': setting.display_name or default_name,
                    'url': dynamic_url,
                    'icon': setting.icon or default_icon,
                    'description': setting.description or default_desc,
                    'is_public': setting.is_public,
                    'min_role_required': setting.min_role_required,
                })
    return user_apps

def get_mounted_app_url(app_name):
    """
    Dynamically scan the root URL configuration to find where the app's urls.py is included.
    """
    resolver = get_resolver()
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            urlconf = pattern.urlconf_module
            module_name = getattr(urlconf, '__name__', str(urlconf))
            if app_name in module_name or pattern.namespace == app_name or pattern.app_name == app_name:
                prefix = str(pattern.pattern).lstrip('^').rstrip('$')
                if not prefix.startswith('/'):
                    prefix = '/' + prefix
                if not prefix.endswith('/'):
                    prefix = prefix + '/'
                return prefix
    return None

def landing_page(request):
    raw_apps = get_installed_user_apps()
    visible_apps = []
    for app_info in raw_apps:
        app_name = app_info['app_name']
        is_public = app_info['is_public']
        min_role = app_info['min_role_required']
        role = get_user_app_role(request.user, app_name)
        
        # Determine accessibility
        can_access = ROLE_LEVELS.get(role, 0) >= ROLE_LEVELS.get(min_role, 1)
        
        # If app is private (not public), hide it completely from users who do not have permission!
        if not is_public and not can_access:
            continue

        app_info['user_role'] = role
        app_info['can_access'] = can_access
        visible_apps.append(app_info)

    return render(request, 'core/landing.html', {
        'apps': visible_apps,
        'user': request.user
    })

def sanitize_next_url(url):
    """
    Sanitize a redirect URL to prevent Open Redirect attacks.
    Only relative paths (no scheme, no netloc) are allowed.
    """
    if not url:
        return '/'
    clean = url.strip()
    # Block absolute URLs: //evil.com, http://evil.com, https://evil.com
    parsed = urlparse(clean)
    if parsed.scheme or parsed.netloc:
        return '/'
    # Block protocol-relative URLs starting with //
    if clean.startswith('//'):
        return '/'
    # Prevent redirect loops back to login/logout
    if clean in ['/login', '/login/', '/logout', '/logout/'] \
            or clean.startswith('/login?') or clean.startswith('/logout?'):
        return '/'
    return clean

def login_view(request):
    raw_next = request.POST.get('next') or request.GET.get('next')
    next_url = sanitize_next_url(raw_next)

    if request.user.is_authenticated:
        return redirect(next_url)

    error_message = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            if not user.is_active:
                error_message = 'บัญชีของคุณถูกระงับการใช้งาน'
            else:
                login(request, user)
                return redirect(next_url)
        else:
            error_message = 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'

    return render(request, 'core/login.html', {
        'next': next_url,
        'error_message': error_message,
    })

def logout_view(request):
    """
    Logout via POST only to prevent CSRF logout attacks.
    GET requests are silently redirected to login without logging out.
    HTTP_REFERER is intentionally ignored to prevent Open Redirect via spoofed headers.
    """
    if request.method != 'POST':
        return redirect('/login/')
    raw_next = request.POST.get('next', '').strip()
    next_url = sanitize_next_url(raw_next) if raw_next else '/login/'
    logout(request)
    return redirect(next_url)


def register_view(request):
    """
    User self-registration endpoint.
    New accounts are created with is_active=False and must be approved by an admin.
    """
    if request.user.is_authenticated:
        return redirect('/')

    errors = {}
    form_data = {}

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        form_data = {
            'username': username,
            'email': email,
        }

        # --- Validation ---
        import re
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as CoreValidationError

        if not username:
            errors['username'] = 'กรุณาระบุชื่อผู้ใช้'
        elif not re.match(r'^[\w.@+-]+$', username):
            errors['username'] = 'ชื่อผู้ใช้มีอักขระที่ไม่อนุญาต (ใช้ได้: ตัวอักษร, ตัวเลข, . @ + - _)'
        elif len(username) < 3:
            errors['username'] = 'ชื่อผู้ใช้ต้องมีอย่างน้อย 3 ตัวอักษร'
        elif len(username) > 150:
            errors['username'] = 'ชื่อผู้ใช้ยาวเกินไป (สูงสุด 150 ตัวอักษร)'
        elif User.objects.filter(username=username).exists():
            errors['username'] = f'ชื่อผู้ใช้ "{username}" มีผู้ใช้งานแล้ว กรุณาเลือกชื่ออื่น'

        if email:
            try:
                validate_email(email)
            except CoreValidationError:
                errors['email'] = 'รูปแบบอีเมลไม่ถูกต้อง'
            else:
                if User.objects.filter(email=email).exists():
                    errors['email'] = 'อีเมลนี้ถูกใช้งานแล้ว'

        if not password:
            errors['password'] = 'กรุณาระบุรหัสผ่าน'
        else:
            try:
                validate_password(password)
            except DjangoValidationError as ve:
                errors['password'] = ' '.join(ve.messages)

        if not errors.get('password'):
            if not confirm_password:
                errors['confirm_password'] = 'กรุณายืนยันรหัสผ่าน'
            elif password != confirm_password:
                errors['confirm_password'] = 'รหัสผ่านไม่ตรงกัน กรุณาตรวจสอบอีกครั้ง'

        if not errors:
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        is_active=False,  # Requires admin approval
                    )
                logger.info(f"New registration: username={username}, email={email}, ip={_get_client_ip_from_request(request)}")
                return render(request, 'core/register.html', {
                    'success': True,
                    'username': username,
                })
            except Exception as e:
                logger.error(f"register_view error: {e}", exc_info=True)
                errors['non_field_errors'] = 'เกิดข้อผิดพลาดในระบบ กรุณาลองใหม่อีกครั้ง'

    return render(request, 'core/register.html', {
        'errors': errors,
        'form_data': form_data,
    })


def _get_client_ip_from_request(request):
    """Resolve real client IP (mirrors signals.py logic)."""
    cf_ip = request.META.get('HTTP_CF_CONNECTING_IP')
    if cf_ip:
        return cf_ip.strip()
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


# ==============================================================================
# Central Admin Dashboard Views & APIs
# ==============================================================================

def staff_member_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.path.startswith('/api/'):
                return JsonResponse({'error': 'กรุณาเข้าสู่ระบบก่อนทำรายการ'}, status=401)
            return redirect(f'/login/?next={request.path}')
        if not (request.user.is_staff or request.user.is_superuser):
            if request.path.startswith('/api/'):
                return JsonResponse({'error': 'ไม่มีสิทธิ์เข้าถึงส่วนผู้ดูแลระบบ'}, status=403)
            return render(request, 'core/permission_denied.html', {
                'display_name': 'Central Admin Dashboard',
                'required_role': 'Staff / Superuser',
                'user_role': 'Standard User',
                'user': request.user
            }, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped_view

@staff_member_required
def admin_dashboard_view(request):
    installed_apps = get_installed_user_apps()
    return render(request, 'core/admin_dashboard.html', {
        'user': request.user,
        'installed_apps': installed_apps,
    })

# --- Users API ---

@csrf_exempt
@staff_member_required
@require_http_methods(["GET", "POST"])
def api_users_list_create(request):
    if request.method == "GET":
        users = User.objects.all().prefetch_related('groups', 'app_permissions').order_by('id')
        installed_apps = get_installed_user_apps()
        user_list = []
        for u in users:
            if u.is_superuser:
                perms = {a['app_name']: 'admin' for a in installed_apps}
            else:
                perms = {p.app_name: p.role for p in u.app_permissions.all()}
            user_list.append({
                'id': u.id,
                'username': u.username,
                'email': u.email,
                'first_name': u.first_name,
                'last_name': u.last_name,
                'is_active': u.is_active,
                'is_staff': u.is_staff,
                'is_superuser': u.is_superuser,
                'date_joined': u.date_joined.strftime('%Y-%m-%d %H:%M') if u.date_joined else '',
                'last_login': u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else 'ยังไม่เคยเข้าใช้งาน',
                'groups': [{'id': g.id, 'name': g.name} for g in u.groups.all()],
                'app_permissions': perms,
            })
        return JsonResponse({'users': user_list})

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            username = str(data.get('username', '')).strip()
            password = str(data.get('password', '')).strip()
            email = str(data.get('email', '')).strip()
            first_name = str(data.get('first_name', '')).strip()
            last_name = str(data.get('last_name', '')).strip()
            is_active = bool(data.get('is_active', True))
            is_staff = bool(data.get('is_staff', False))
            is_superuser = bool(data.get('is_superuser', False))
            if is_superuser:
                is_staff = True
            group_ids = data.get('groups', [])
            app_perms = data.get('app_permissions', {})

            if not username:
                return JsonResponse({'error': 'กรุณาระบุชื่อผู้ใช้ (Username)'}, status=400)
            if not password:
                return JsonResponse({'error': 'กรุณาระบุรหัสผ่าน (Password)'}, status=400)
            if User.objects.filter(username=username).exists():
                return JsonResponse({'error': f'ชื่อผู้ใช้ "{username}" มีอยู่ในระบบแล้ว'}, status=400)

            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=is_active,
                    is_staff=is_staff,
                    is_superuser=is_superuser
                )
                
                # Groups
                if group_ids:
                    groups = Group.objects.filter(id__in=group_ids)
                    user.groups.set(groups)

                # App permissions (Superusers always have admin on all apps)
                if not is_superuser:
                    for app_name, role in app_perms.items():
                        if role in ROLE_LEVELS:
                            UserAppPermission.objects.create(user=user, app_name=app_name, role=role)

            return JsonResponse({'success': True, 'id': user.id, 'username': user.username})
        except Exception as e:
            logger.error(f"api_users_list_create POST error: {e}", exc_info=True)
            return JsonResponse({'error': 'เกิดข้อผิดพลาด กรุณาลองอีกครั้ง'}, status=400)

@csrf_exempt
@staff_member_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_user_detail(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method == "GET":
        installed_apps = get_installed_user_apps()
        if user.is_superuser:
            perms = {a['app_name']: 'admin' for a in installed_apps}
        else:
            perms = {p.app_name: p.role for p in user.app_permissions.all()}
        return JsonResponse({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_active': user.is_active,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'groups': [g.id for g in user.groups.all()],
            'app_permissions': perms
        })

    elif request.method == "PUT":
        try:
            data = json.loads(request.body)
            username = str(data.get('username', '')).strip()
            password = str(data.get('password', '')).strip()
            email = str(data.get('email', '')).strip()
            first_name = str(data.get('first_name', '')).strip()
            last_name = str(data.get('last_name', '')).strip()
            is_active = data.get('is_active')
            is_staff = data.get('is_staff')
            is_superuser = data.get('is_superuser')
            group_ids = data.get('groups')
            app_perms = data.get('app_permissions')

            if username and username != user.username:
                if User.objects.filter(username=username).exclude(id=user.id).exists():
                    return JsonResponse({'error': f'ชื่อผู้ใช้ "{username}" มีอยู่ในระบบแล้ว'}, status=400)
                user.username = username

            if email is not None:
                user.email = email
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            if is_active is not None:
                user.is_active = bool(is_active)
            if is_superuser is not None:
                user.is_superuser = bool(is_superuser)
                if user.is_superuser:
                    user.is_staff = True
            elif is_staff is not None:
                user.is_staff = bool(is_staff)

            if password:
                user.set_password(password)

            with transaction.atomic():
                user.save()

                if group_ids is not None:
                    groups = Group.objects.filter(id__in=group_ids)
                    user.groups.set(groups)

                if user.is_superuser:
                    # Superusers always have admin on all apps, clean any lower perms
                    UserAppPermission.objects.filter(user=user).delete()
                elif app_perms is not None and isinstance(app_perms, dict):
                    UserAppPermission.objects.filter(user=user).delete()
                    for app_name, role in app_perms.items():
                        if role in ROLE_LEVELS:
                            UserAppPermission.objects.create(user=user, app_name=app_name, role=role)

            return JsonResponse({'success': True, 'id': user.id})
        except Exception as e:
            logger.error(f"api_user_detail PUT error user={user_id}: {e}", exc_info=True)
            return JsonResponse({'error': 'เกิดข้อผิดพลาด กรุณาลองอีกครั้ง'}, status=400)

    elif request.method == "DELETE":
        if request.user.id == user.id:
            return JsonResponse({'error': 'ไม่สามารถลบบัญชีของตัวคุณเองที่กำลังเข้าสู่ระบบอยู่ได้'}, status=400)
        
        user.delete()
        return JsonResponse({'success': True})

# --- Groups API ---

@csrf_exempt
@staff_member_required
@require_http_methods(["GET", "POST"])
def api_groups_list_create(request):
    if request.method == "GET":
        groups = Group.objects.all().prefetch_related('user_set', 'app_permissions').order_by('id')
        group_list = []
        for g in groups:
            perms = {p.app_name: p.role for p in g.app_permissions.all()}
            group_list.append({
                'id': g.id,
                'name': g.name,
                'member_count': g.user_set.count(),
                'members': [{'id': u.id, 'username': u.username} for u in g.user_set.all()],
                'app_permissions': perms
            })
        return JsonResponse({'groups': group_list})

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            name = str(data.get('name', '')).strip()
            member_ids = data.get('members', [])
            app_perms = data.get('app_permissions', {})

            if not name:
                return JsonResponse({'error': 'กรุณาระบุชื่อกลุ่ม (Group Name)'}, status=400)
            if Group.objects.filter(name=name).exists():
                return JsonResponse({'error': f'กลุ่มชื่อ "{name}" มีอยู่ในระบบแล้ว'}, status=400)

            with transaction.atomic():
                group = Group.objects.create(name=name)

                if member_ids:
                    users = User.objects.filter(id__in=member_ids)
                    group.user_set.set(users)

                for app_name, role in app_perms.items():
                    if role in ROLE_LEVELS:
                        GroupAppPermission.objects.create(group=group, app_name=app_name, role=role)

            return JsonResponse({'success': True, 'id': group.id, 'name': group.name})
        except Exception as e:
            logger.error(f"api_groups_list_create POST error: {e}", exc_info=True)
            return JsonResponse({'error': 'เกิดข้อผิดพลาด กรุณาลองอีกครั้ง'}, status=400)

@csrf_exempt
@staff_member_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_group_detail(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    if request.method == "GET":
        perms = {p.app_name: p.role for p in group.app_permissions.all()}
        return JsonResponse({
            'id': group.id,
            'name': group.name,
            'members': [u.id for u in group.user_set.all()],
            'app_permissions': perms
        })

    elif request.method == "PUT":
        try:
            data = json.loads(request.body)
            name = str(data.get('name', '')).strip()
            member_ids = data.get('members')
            app_perms = data.get('app_permissions')

            if name and name != group.name:
                if Group.objects.filter(name=name).exclude(id=group.id).exists():
                    return JsonResponse({'error': f'กลุ่มชื่อ "{name}" มีอยู่ในระบบแล้ว'}, status=400)
                group.name = name

            with transaction.atomic():
                group.save()

                if member_ids is not None:
                    users = User.objects.filter(id__in=member_ids)
                    group.user_set.set(users)

                if app_perms is not None and isinstance(app_perms, dict):
                    GroupAppPermission.objects.filter(group=group).delete()
                    for app_name, role in app_perms.items():
                        if role in ROLE_LEVELS:
                            GroupAppPermission.objects.create(group=group, app_name=app_name, role=role)

            return JsonResponse({'success': True, 'id': group.id})
        except Exception as e:
            logger.error(f"api_group_detail PUT error group={group_id}: {e}", exc_info=True)
            return JsonResponse({'error': 'เกิดข้อผิดพลาด กรุณาลองอีกครั้ง'}, status=400)

    elif request.method == "DELETE":
        group.delete()
        return JsonResponse({'success': True})

# --- App Settings API ---

@csrf_exempt
@staff_member_required
@require_http_methods(["GET"])
def api_app_settings_list(request):
    apps_list = get_installed_user_apps()
    return JsonResponse({'apps': apps_list})

@csrf_exempt
@staff_member_required
@require_http_methods(["PUT"])
def api_app_setting_detail(request, app_name):
    try:
        data = json.loads(request.body)
        setting = get_app_setting(app_name)

        if 'is_public' in data:
            setting.is_public = bool(data['is_public'])
        if 'display_name' in data:
            setting.display_name = str(data['display_name']).strip()
        if 'icon' in data:
            setting.icon = str(data['icon']).strip()
        if 'description' in data:
            setting.description = str(data['description']).strip()
        if 'min_role_required' in data:
            role = str(data['min_role_required']).strip()
            if role in ROLE_LEVELS:
                setting.min_role_required = role

        setting.save()
        return JsonResponse({
            'success': True,
            'app_name': setting.app_name,
            'is_public': setting.is_public,
            'min_role_required': setting.min_role_required,
            'display_name': setting.display_name,
            'icon': setting.icon,
            'description': setting.description
        })
    except Exception as e:
        logger.error(f"api_app_setting_detail PUT error app={app_name}: {e}", exc_info=True)
        return JsonResponse({'error': 'เกิดข้อผิดพลาด กรุณาลองอีกครั้ง'}, status=400)

# --- Login Logs API ---

@csrf_exempt
@staff_member_required
@require_http_methods(["GET"])
def api_login_logs_list(request):
    user_id = request.GET.get('user_id')
    status = request.GET.get('status')
    search = request.GET.get('search', '').strip()
    limit = min(int(request.GET.get('limit', 100)), 500)  # Cap at 500 to prevent DoS

    qs = UserLoginLog.objects.all().select_related('user').order_by('-timestamp')

    if user_id:
        qs = qs.filter(user_id=user_id)
    if status and status in ['success', 'failed']:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(username_attempted__icontains=search) | qs.filter(ip_address__icontains=search)

    logs = []
    for log in qs[:limit]:
        logs.append({
            'id': log.id,
            'user_id': log.user_id,
            'username': log.username_attempted or (log.user.username if log.user else 'Unknown'),
            'ip_address': log.ip_address or '-',
            'user_agent': log.user_agent or '-',
            'status': log.status,
            'failure_reason': log.failure_reason or '',
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        })

    return JsonResponse({'logs': logs})

@csrf_exempt
@staff_member_required
@require_http_methods(["GET"])
def api_user_login_logs(request, user_id):
    user = get_object_or_404(User, id=user_id)
    logs = [
        {
            'id': log.id,
            'username': log.username_attempted or user.username,
            'ip_address': log.ip_address or '-',
            'user_agent': log.user_agent or '-',
            'status': log.status,
            'failure_reason': log.failure_reason or '',
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        }
        for log in UserLoginLog.objects.filter(user=user).order_by('-timestamp')[:50]
    ]
    return JsonResponse({'username': user.username, 'logs': logs})


# --- Pending Registrations API ---

@csrf_exempt
@staff_member_required
@require_http_methods(["GET"])
def api_pending_registrations(request):
    """
    List all users with is_active=False (pending admin approval).
    """
    pending = User.objects.filter(is_active=False).order_by('date_joined')
    data = [
        {
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'date_joined': u.date_joined.strftime('%Y-%m-%d %H:%M') if u.date_joined else '',
        }
        for u in pending
    ]
    return JsonResponse({'pending': data, 'count': len(data)})


@csrf_exempt
@staff_member_required
@require_http_methods(["POST"])
def api_approve_registration(request, user_id):
    """
    Approve (activate) a pending registration.
    """
    user = get_object_or_404(User, id=user_id, is_active=False)
    user.is_active = True
    user.save(update_fields=['is_active'])
    logger.info(f"Admin {request.user.username} approved registration for user {user.username} (id={user.id})")
    return JsonResponse({'success': True, 'username': user.username})


@csrf_exempt
@staff_member_required
@require_http_methods(["DELETE"])
def api_reject_registration(request, user_id):
    """
    Reject (delete) a pending registration.
    """
    user = get_object_or_404(User, id=user_id, is_active=False)
    username = user.username
    user.delete()
    logger.info(f"Admin {request.user.username} rejected and deleted registration for user {username}")
    return JsonResponse({'success': True, 'username': username})


