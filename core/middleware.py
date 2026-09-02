"""
core/middleware.py

Security middleware for production deployment.
"""


class RobotsHeaderMiddleware:
    """
    Adds  X-Robots-Tag: noindex, nofollow, noai, noimageai  to every HTTP
    response so that search engines and AI scrapers that respect headers
    will not index or archive any page on this application.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['X-Robots-Tag'] = 'noindex, nofollow, noarchive, nosnippet, noai, noimageai'
        return response


class ContentSecurityPolicyMiddleware:
    """
    Injects a Content-Security-Policy header on every response to mitigate
    XSS, data injection, and clickjacking attacks.

    Directives:
    - default-src 'self'         : only same-origin by default
    - script-src 'self'          : no inline scripts (blocks XSS payloads)
    - style-src 'self' + fonts   : allow Google Fonts stylesheets
    - font-src 'self' + fonts    : allow Google Fonts font files
    - img-src 'self' data: blob: : allow embedded images and media uploads
    - connect-src 'self'         : API calls to same origin only
    - frame-ancestors 'none'     : prevents clickjacking (same as X-Frame-Options: DENY)
    - base-uri 'self'            : prevents base-tag injection
    - form-action 'self'         : form submissions must target same origin
    """

    CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com; "  # unsafe-inline required for inline <script> blocks in templates
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob: /media/ https://mc-heads.net https://*.mc-heads.net https://crafatar.com https://minotar.net; "
        "connect-src 'self' ws: wss: https://cloudflareinsights.com; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Don't override if already set (e.g., by a specific view)
        if 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = self.CSP
        return response
