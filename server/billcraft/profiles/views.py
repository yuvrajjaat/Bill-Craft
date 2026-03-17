import json

from bson import ObjectId
from pymongo import ReturnDocument
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from billcraft.db import get_collection
from billcraft.auth_middleware import jwt_required


def _profile_to_dict(profile):
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
@jwt_required
def profile_list(request):
    """GET /profiles - List profiles; POST /profiles - Create profile."""
    profiles = get_collection('profiles')

    if request.method == 'GET':
        search_query = request.GET.get('searchQuery', '')
        # Frontend passes userId as searchQuery for profiles
        if search_query:
            query = {'userId': search_query}
        else:
            query = {'userId': request.user_id}

        results = profiles.find(query)
        data = [_profile_to_dict(p) for p in results]
        return JsonResponse(data, safe=False)

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
            profile_data = {
                'name': body.get('name', ''),
                'email': body.get('email', ''),
                'phoneNumber': body.get('phoneNumber', ''),
                'businessName': body.get('businessName', ''),
                'contactAddress': body.get('contactAddress', ''),
                'paymentDetails': body.get('paymentDetails', ''),
                'logo': body.get('logo', ''),
                'website': body.get('website', ''),
                'userId': body.get('userId', request.user_id),
            }

            result = profiles.insert_one(profile_data)
            profile_data['_id'] = str(result.inserted_id)
            return JsonResponse(profile_data, status=201)

        except Exception as e:
            return JsonResponse({'message': 'Something went wrong'}, status=500)

    return JsonResponse({'message': 'Method not allowed'}, status=405)


@csrf_exempt
@jwt_required
@require_http_methods(['GET', 'PATCH', 'DELETE'])
def profile_detail(request, pk):
    """GET/PATCH/DELETE /profiles/{id}"""
    profiles = get_collection('profiles')

    try:
        oid = ObjectId(pk)
    except Exception:
        return JsonResponse({'message': f'Invalid id: {pk}'}, status=400)

    if request.method == 'GET':
        profile = profiles.find_one({'_id': oid})
        if not profile:
            return JsonResponse({'message': f'Profile not found with id: {pk}'}, status=404)
        return JsonResponse(_profile_to_dict(profile))

    elif request.method == 'PATCH':
        body = json.loads(request.body)
        update_fields = {}
        for field in ['name', 'email', 'phoneNumber', 'businessName',
                      'contactAddress', 'paymentDetails', 'logo', 'website']:
            if field in body and body[field] is not None:
                update_fields[field] = body[field]

        if not update_fields:
            return JsonResponse({'message': 'No fields to update'}, status=400)

        result = profiles.find_one_and_update(
            {'_id': oid},
            {'$set': update_fields},
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            return JsonResponse({'message': f'Profile not found with id: {pk}'}, status=404)
        return JsonResponse(_profile_to_dict(result))

    elif request.method == 'DELETE':
        result = profiles.delete_one({'_id': oid})
        if result.deleted_count == 0:
            return JsonResponse({'message': f'Profile not found with id: {pk}'}, status=404)
        return JsonResponse({'message': 'Profile deleted successfully'})
