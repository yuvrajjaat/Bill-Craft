import traceback


class ErrorLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        print(f"\n>>> {request.method} {request.path}")
        try:
            response = self.get_response(request)
            print(f"<<< {response.status_code}")
            return response
        except Exception as e:
            print(f"!!! EXCEPTION: {e}")
            traceback.print_exc()
            raise
