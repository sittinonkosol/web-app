"""
Rate Limiting Middleware for SC Quiz
กำหนดขีดจำกัดการส่งข้อความต่อ IP ต่อนาที โดยใช้ Redis Cache
และดึง Cooldown Settings จาก QuizSession ที่ Active
"""
import time
import json
from django.http import JsonResponse
from django.core.cache import cache


def get_real_ip(request):
    """ดึง Real IP จาก X-Forwarded-For (Cloudflare) หรือ REMOTE_ADDR"""
    cf_ip = request.META.get('HTTP_CF_CONNECTING_IP')
    if cf_ip:
        return cf_ip.strip()
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


class RateLimitMiddleware:
    """
    Middleware จำกัดจำนวนการส่งข้อความต่อ IP ต่อนาที
    อ่านค่า rate_limit_per_minute จาก QuizSession ที่ Active
    รวมถึงป้องกัน Brute Force บนหน้า Login ด้วย
    """
    RATE_LIMITED_PATHS = ['/api/messages']
    # Login brute force: max 10 attempts/min per IP (fixed, not configurable)
    LOGIN_PATHS = ['/login/', '/ict/scquizz/login']
    LOGIN_LIMIT = 10
    LOGIN_WINDOW = 60  # seconds

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # --- Login brute force protection ---
        if request.method == 'POST' and any(
            request.path.rstrip('/') == p.rstrip('/') for p in self.LOGIN_PATHS
        ):
            response = self._check_login_rate_limit(request)
            if response:
                return response

        # --- Message rate limiting ---
        if request.method == 'POST' and any(
            request.path.rstrip('/').endswith(p) for p in self.RATE_LIMITED_PATHS
        ):
            response = self._check_rate_limit(request)
            if response:
                return response
        return self.get_response(request)

    def _check_login_rate_limit(self, request):
        """Fixed rate limit for login: 10 POST attempts per minute per IP."""
        ip = get_real_ip(request)
        key = f'loginlimit:count:{ip}:{int(time.time() // self.LOGIN_WINDOW)}'
        count = cache.get(key, 0)
        if count >= self.LOGIN_LIMIT:
            from django.http import HttpResponse
            return HttpResponse(
                'เกินจำนวนครั้งที่อนุญาต กรุณารอ 1 นาทีแล้วลองใหม่',
                status=429,
                content_type='text/plain; charset=utf-8'
            )
        cache.set(key, count + 1, timeout=self.LOGIN_WINDOW)
        return None

    def _check_rate_limit(self, request):
        from scquizz.models import QuizSession

        # ดึง Session ที่ Active
        session = QuizSession.objects.filter(is_active=True).first()
        if not session:
            session = QuizSession.objects.first()

        # ถ้าไม่มี session หรือ limit = 0 → ไม่จำกัด
        if not session or session.rate_limit_per_minute == 0:
            return None

        limit = session.rate_limit_per_minute
        cooldown = session.cooldown_seconds
        ip = get_real_ip(request)
        window = 60  # วินาที

        # Key สำหรับ Counter ต่อนาที
        count_key = f'ratelimit:count:{ip}:{int(time.time() // window)}'
        # Key สำหรับ Cooldown ต่อ IP
        cooldown_key = f'ratelimit:cooldown:{ip}'

        # ตรวจสอบ Cooldown ก่อน
        expire_time = cache.get(cooldown_key)
        if expire_time is not None and cooldown > 0:
            ttl = max(1, int(expire_time - time.time()))
            resp = JsonResponse({
                'error': f'กรุณารอ {ttl} วินาทีก่อนส่งข้อความถัดไป',
                'retry_after': ttl,
                'cooldown': True,
            }, status=429)
            resp['Retry-After'] = str(ttl)
            resp['X-Cooldown-Seconds'] = str(cooldown)
            return resp

        # นับและตรวจสอบ Rate Limit ต่อนาที
        count = cache.get(count_key, 0)
        if count >= limit:
            resp = JsonResponse({
                'error': f'ส่งข้อความเกินขีดจำกัด ({limit} ครั้ง/นาที) กรุณารอสักครู่',
                'retry_after': window,
                'cooldown': False,
            }, status=429)
            resp['Retry-After'] = str(window)
            resp['X-Cooldown-Seconds'] = str(cooldown)
            return resp

        # เพิ่ม Counter
        cache.set(count_key, count + 1, timeout=window)
        # ตั้ง Cooldown หลังส่งสำเร็จ (ตั้งผ่าน response header ให้ frontend จัดการ)
        # Middleware แค่ส่ง header กลับไป — ไม่ block ตัวเอง
        request._rate_limit_cooldown = cooldown
        return None
