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
