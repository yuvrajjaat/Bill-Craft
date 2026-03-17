"""JWT authentication middleware and utilities."""
import json
import base64
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from django.conf import settings
from django.http import JsonResponse


def generate_token(email, user_id):
    """Generate a JWT token with email and id claims."""
    expiry_seconds = settings.JWT_EXPIRATION_MS / 1000
    payload = {
        'email': email,
        'id': str(user_id),
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm='HS256')


def decode_token(token):
    """Decode a JWT token. Returns the payload dict or None."""
    try:
        # Check if it's a Google token (length >= 500)
        if len(token) >= 500:
            # Decode Google JWT payload (middle segment) without verification
            parts = token.split('.')
            if len(parts) >= 2:
                payload_segment = parts[1]
                # Add padding
                padding = 4 - len(payload_segment) % 4
                if padding != 4:
                    payload_segment += '=' * padding
                decoded = base64.urlsafe_b64decode(payload_segment)
                data = json.loads(decoded)
                return {'id': data.get('sub'), 'email': data.get('email')}
            return None
        else:
            # Custom JWT
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=['HS256'])
            return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception):
        return None


def jwt_required(view_func):
    """Decorator to require JWT authentication on a view."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return JsonResponse({'message': 'Authentication required'}, status=401)

        token = auth_header[7:]  # Remove "Bearer "
        payload = decode_token(token)
        if payload is None:
            return JsonResponse({'message': 'Invalid or expired token'}, status=401)

        request.user_id = payload.get('id')
        request.user_email = payload.get('email')
        return view_func(request, *args, **kwargs)

    return wrapper
