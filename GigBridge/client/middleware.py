from client.currency import set_current_request


class CurrencyRequestMiddleware:
    """
    Middleware that captures the current HTTP request into thread-local storage.
    Enables template filters like {{ amount|money }} and helpers to automatically
    access active cookies, user profile display currency, and Accept-Language headers
    without requiring manual context passing on every filter call.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_request(request)
        response = self.get_response(request)
        set_current_request(None)
        return response
