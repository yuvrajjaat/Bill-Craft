import json
import math
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from billcraft.db import get_collection
from billcraft.auth_middleware import jwt_required


def _client_to_dict(client):
    return {
        '_id': str(client['_id']),
        'name': client.get('name', ''),
        'email': client.get('email', ''),
        'phone': client.get('phone', ''),
        'address': client.get('address', ''),
        'userId': str(client.get('userId', '')),
        'createdAt': client.get('createdAt', ''),
    }


@csrf_exempt
@jwt_required
def get_clients_by_user(request):
    """GET /clients/user - Get all clients for authenticated user (no pagination)."""
    if request.method != 'GET':
        return JsonResponse({'message': 'Method not allowed'}, status=405)

    search_query = request.GET.get('searchQuery', '')
    clients = get_collection('clients')

    # Frontend passes userId as searchQuery
    if search_query:
        query = {'userId': search_query}
    else:
        query = {'userId': request.user_id}

    results = clients.find(query).sort('createdAt', -1)
    data = [_client_to_dict(c) for c in results]
    return JsonResponse(data, safe=False)


@csrf_exempt
@jwt_required
def get_clients_paginated(request):
    """GET /clients/all - Get paginated clients."""
    if request.method != 'GET':
        return JsonResponse({'message': 'Method not allowed'}, status=405)

    page = int(request.GET.get('page', 1))
    search_query = request.GET.get('searchQuery', '')
    limit = 8

    clients = get_collection('clients')
    query = {'userId': request.user_id}
    if search_query:
        query['name'] = {'$regex': search_query, '$options': 'i'}

    total_count = clients.count_documents(query)
    number_of_pages = math.ceil(total_count / limit) if total_count > 0 else 1
    skip = (page - 1) * limit

    results = clients.find(query).sort('createdAt', -1).skip(skip).limit(limit)
    data = [_client_to_dict(c) for c in results]

    return JsonResponse({
        'data': data,
        'currentPage': page,
        'numberOfPages': number_of_pages,
        'totalCount': total_count,
    })


@csrf_exempt
@jwt_required
def create_client(request):
    """POST /clients - Create a new client."""
    if request.method != 'POST':
        return JsonResponse({'message': 'Method not allowed'}, status=405)

    try:
        body = json.loads(request.body)
        clients = get_collection('clients')

        client_data = {
            'name': body.get('name', ''),
            'email': body.get('email', ''),
            'phone': body.get('phone', ''),
            'address': body.get('address', ''),
            'userId': body.get('userId', request.user_id),
            'createdAt': datetime.now(timezone.utc).isoformat(),
        }

        result = clients.insert_one(client_data)
        client_data['_id'] = str(result.inserted_id)
        return JsonResponse(client_data, status=201)

    except Exception as e:
        return JsonResponse({'message': 'Something went wrong'}, status=500)


@csrf_exempt
@jwt_required
@require_http_methods(['GET', 'PATCH', 'DELETE'])
def client_detail(request, pk):
    """GET/PATCH/DELETE /clients/{id}"""
    clients = get_collection('clients')

    try:
        oid = ObjectId(pk)
    except Exception:
        return JsonResponse({'message': f'Invalid id: {pk}'}, status=400)

    if request.method == 'GET':
        client = clients.find_one({'_id': oid})
        if not client:
            return JsonResponse({'message': f'Client not found with id: {pk}'}, status=404)
        return JsonResponse(_client_to_dict(client))

    elif request.method == 'PATCH':
        body = json.loads(request.body)
        update_fields = {}
        for field in ['name', 'email', 'phone', 'address']:
            if field in body and body[field] is not None:
                update_fields[field] = body[field]

        if not update_fields:
            return JsonResponse({'message': 'No fields to update'}, status=400)

        result = clients.find_one_and_update(
            {'_id': oid},
            {'$set': update_fields},
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            return JsonResponse({'message': f'Client not found with id: {pk}'}, status=404)
        return JsonResponse(_client_to_dict(result))

    elif request.method == 'DELETE':
        result = clients.delete_one({'_id': oid})
        if result.deleted_count == 0:
            return JsonResponse({'message': f'Client not found with id: {pk}'}, status=404)
        return JsonResponse({'message': 'Client deleted successfully'})
