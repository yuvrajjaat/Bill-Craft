import json
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail

from billcraft.db import get_collection
from billcraft.auth_middleware import generate_token


def _hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def _user_to_dict(user):
    return {
        '_id': str(user['_id']),
        'name': user.get('name', ''),
        'email': user.get('email', ''),
    }


def _profile_to_dict(profile):
    if profile is None:
        return None
    return {
        '_id': str(profile['_id']),
        'name': profile.get('name', ''),
        'email': profile.get('email', ''),
        'phoneNumber': profile.get('phoneNumber', ''),
        'businessName': profile.get('businessName', ''),
        'contactAddress': profile.get('contactAddress', ''),
        'paymentDetails': profile.get('paymentDetails', ''),
        'logo': profile.get('logo', ''),
        'website': profile.get('website', ''),
        'userId': str(profile.get('userId', '')),
    }


@csrf_exempt
@require_POST
def signin(request):
    try:
        body = json.loads(request.body)
        email = body.get('email', '').strip()
        password = body.get('password', '')

        if not email or not password:
            return JsonResponse({'message': 'Email and password are required'}, status=400)

        users = get_collection('users')
        user = users.find_one({'email': email})

        if not user:
            return JsonResponse({'message': 'User not found'}, status=400)

        if not _check_password(password, user['password']):
            return JsonResponse({'message': 'Invalid credentials'}, status=400)

        token = generate_token(user['email'], user['_id'])
        return JsonResponse({
            'result': _user_to_dict(user),
            'token': token,
            'userProfile': None,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'message': 'Something went wrong'}, status=500)


@csrf_exempt
@require_POST
def signup(request):
    try:
        body = json.loads(request.body)
        first_name = body.get('firstName', '').strip()
        last_name = body.get('lastName', '').strip()
        email = body.get('email', '').strip()
        password = body.get('password', '')
        confirm_password = body.get('confirmPassword', '')

        if not first_name or not last_name or not email or not password:
            return JsonResponse({'message': 'All fields are required'}, status=400)

        if len(password) < 6:
            return JsonResponse({'message': 'Password must be at least 6 characters'}, status=400)

        if password != confirm_password:
            return JsonResponse({"message": "Passwords don't match"}, status=400)

        users = get_collection('users')
        existing = users.find_one({'email': email})
        if existing:
            return JsonResponse({'message': 'User already exists'}, status=400)

        name = f"{first_name} {last_name}"
        hashed = _hash_password(password)

        result = users.insert_one({
            'name': name,
            'email': email,
            'password': hashed,
            'resetToken': None,
            'expireToken': None,
        })
        user_id = result.inserted_id

        # Auto-create profile
        profiles = get_collection('profiles')
        profile_result = profiles.insert_one({
            'name': name,
            'email': email,
            'phoneNumber': '',
            'businessName': '',
            'contactAddress': '',
            'paymentDetails': '',
            'logo': '',
            'website': '',
            'userId': str(user_id),
        })

        user_data = {
            '_id': str(user_id),
            'name': name,
            'email': email,
        }

        profile_data = {
            '_id': str(profile_result.inserted_id),
            'name': name,
            'email': email,
            'userId': str(user_id),
        }

        token = generate_token(email, user_id)
        return JsonResponse({
            'result': user_data,
            'token': token,
            'userProfile': profile_data,
        }, status=201)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'message': 'Something went wrong'}, status=500)


@csrf_exempt
@require_POST
def forgot(request):
    try:
        body = json.loads(request.body)
        email = body.get('email', '').strip()

        users = get_collection('users')
        user = users.find_one({'email': email})

        if not user:
            return JsonResponse({'message': 'User with this email does not exist'}, status=404)

        # Generate reset token
        reset_token = secrets.token_hex(32)  # 64-char hex string
        expire_time = datetime.now(timezone.utc) + timedelta(hours=1)

        users.update_one(
            {'_id': user['_id']},
            {'$set': {'resetToken': reset_token, 'expireToken': expire_time}}
        )

        # Send email
        frontend_url = settings.FRONTEND_URL
        reset_link = f"{frontend_url}/reset/{reset_token}"

        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Password Reset Request</h2>
            <p>You requested a password reset. Click the link below to reset your password:</p>
            <p><a href="{reset_link}" style="background-color: #6366f1; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Reset Password</a></p>
            <p>This link will expire in 1 hour.</p>
            <p>If you didn't request this, please ignore this email.</p>
        </body>
        </html>
        """

        try:
            send_mail(
                subject='Password Reset - BillCraft',
                message='',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as email_err:
            print(f"Email sending failed: {email_err}")

        return JsonResponse({'message': 'Check your email for the reset link'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'message': 'Something went wrong'}, status=500)


@csrf_exempt
@require_POST
def reset(request):
    try:
        body = json.loads(request.body)
        token = body.get('token', '')
        password = body.get('password', '')

        if not token or not password:
            return JsonResponse({'message': 'Token and password are required'}, status=400)

        if len(password) < 6:
            return JsonResponse({'message': 'Password must be at least 6 characters'}, status=400)

        users = get_collection('users')
        user = users.find_one({'resetToken': token})

        if not user:
            return JsonResponse({'message': 'Invalid or expired token'}, status=400)

        expire_token = user.get('expireToken')
        if expire_token and expire_token.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            return JsonResponse({'message': 'Token has expired. Try again.'}, status=400)

        hashed = _hash_password(password)
        users.update_one(
            {'_id': user['_id']},
            {'$set': {'password': hashed, 'resetToken': None, 'expireToken': None}}
        )

        return JsonResponse({'message': 'Password successfully updated'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'message': 'Something went wrong'}, status=500)
