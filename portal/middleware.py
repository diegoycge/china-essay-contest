from django.conf import settings


class NoStoreMiddleware:
    """Response headers that apply to every page.

    `Cache-Control: no-store` keeps essays and scores out of browser and proxy
    caches: without it, the back button after signing out on a shared computer
    could still show an essay or a score sheet. The content security policy is
    a second line of defence should essay text ever be rendered unescaped.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/static/") and "Cache-Control" not in response:
            response["Cache-Control"] = "no-store"
        response.setdefault("Content-Security-Policy", settings.CONTENT_SECURITY_POLICY)
        return response
