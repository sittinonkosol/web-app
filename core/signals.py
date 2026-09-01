from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver
from .models import UserLoginLog

# Use the same trusted IP resolution as the middleware (respects CF-Connecting-IP first)
def _get_client_ip(request):
    """
    Resolve the real client IP.
    Priority: CF-Connecting-IP (Cloudflare) > X-Forwarded-For first entry > REMOTE_ADDR
    Mirrors get_real_ip() in scquizz/middleware.py to avoid IP spoofing in logs.
    """
    if not request:
        return ''
    cf_ip = request.META.get('HTTP_CF_CONNECTING_IP')
    if cf_ip:
        return cf_ip.strip()
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')

def _get_client_user_agent(request):
    if not request:
        return ''
    return request.META.get('HTTP_USER_AGENT', '')[:512]  # cap length

@receiver(user_logged_in)
def log_user_logged_in(sender, request, user, **kwargs):
    UserLoginLog.objects.create(
        user=user,
        username_attempted=user.username,
        ip_address=_get_client_ip(request),
        user_agent=_get_client_user_agent(request),
        status='success'
    )

@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    username = credentials.get('username', '') if credentials else ''
    UserLoginLog.objects.create(
        user=None,
        username_attempted=username or 'Unknown',
        ip_address=_get_client_ip(request),
        user_agent=_get_client_user_agent(request),
        status='failed',
        failure_reason='ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'
    )
