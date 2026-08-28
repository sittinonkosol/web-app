from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver
from .models import UserLoginLog

def get_client_ip(request):
    if not request:
        return ''
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip

def get_client_user_agent(request):
    if not request:
        return ''
    return request.META.get('HTTP_USER_AGENT', '')

@receiver(user_logged_in)
def log_user_logged_in(sender, request, user, **kwargs):
    UserLoginLog.objects.create(
        user=user,
        username_attempted=user.username,
        ip_address=get_client_ip(request),
        user_agent=get_client_user_agent(request),
        status='success'
    )

@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    username = credentials.get('username', '') if credentials else ''
    UserLoginLog.objects.create(
        user=None,
        username_attempted=username or 'Unknown',
        ip_address=get_client_ip(request),
        user_agent=get_client_user_agent(request),
        status='failed',
        failure_reason='ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'
    )
