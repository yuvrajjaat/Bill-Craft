import json
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from billcraft.db import get_collection
from billcraft.auth_middleware import jwt_required


def _invoice_to_dict(inv):
    created_at = inv.get('createdAt', '')
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    due_date = inv.get('dueDate', '')
    if isinstance(due_date, datetime):
        due_date = due_date.isoformat()

    payment_records = []
    for pr in inv.get('paymentRecords', []):
        dp = pr.get('datePaid', '')
        if isinstance(dp, datetime):
            dp = dp.isoformat()
        payment_records.append({
            'amountPaid': pr.get('amountPaid', 0),
            'datePaid': dp,
            'paymentMethod': pr.get('paymentMethod', ''),
            'note': pr.get('note', ''),
            'paidBy': pr.get('paidBy', ''),
        })

    return {
        '_id': str(inv['_id']),
        'invoiceNumber': inv.get('invoiceNumber', ''),
        'type': inv.get('type', 'Invoice'),
        'status': inv.get('status', 'Unpaid'),
        'currency': inv.get('currency', ''),
        'dueDate': due_date,
        'createdAt': created_at,
        'client': inv.get('client', {}),
        'items': inv.get('items', []),
        'subTotal': inv.get('subTotal', 0),
        'vat': inv.get('vat', 0),
        'total': inv.get('total', 0),
        'totalAmountReceived': inv.get('totalAmountReceived', 0),
        'rates': inv.get('rates', ''),
        'notes': inv.get('notes', ''),
        'creator': str(inv.get('creator', '')),
        'paymentRecords': payment_records,
    }


@csrf_exempt
@jwt_required
def invoice_list(request):
    """GET /invoices - List invoices; POST /invoices - Create invoice."""
    invoices = get_collection('invoices')

    if request.method == 'GET':
        search_query = request.GET.get('searchQuery', '')
        # Frontend passes userId as searchQuery
        if search_query:
            query = {'creator': search_query}
        else:
            query = {'creator': request.user_id}

        results = invoices.find(query).sort('createdAt', -1)
        data = [_invoice_to_dict(inv) for inv in results]
        return JsonResponse(data, safe=False)

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
            invoice_data = {
                'invoiceNumber': body.get('invoiceNumber', ''),
                'type': body.get('type', 'Invoice'),
                'status': body.get('status', 'Unpaid'),
                'currency': body.get('currency', ''),
                'dueDate': body.get('dueDate', ''),
                'createdAt': datetime.now(timezone.utc).isoformat(),
                'client': body.get('client', {}),
                'items': body.get('items', []),
                'subTotal': body.get('subTotal', 0),
                'vat': body.get('vat', 0),
                'total': body.get('total', 0),
                'totalAmountReceived': body.get('totalAmountReceived', 0.0),
                'rates': body.get('rates', ''),
                'notes': body.get('notes', ''),
                'creator': body.get('creator', request.user_id),
                'paymentRecords': body.get('paymentRecords', []),
            }

            result = invoices.insert_one(invoice_data)
            invoice_data['_id'] = str(result.inserted_id)
            return JsonResponse(invoice_data, status=201)

        except Exception as e:
            return JsonResponse({'message': 'Something went wrong'}, status=500)

    return JsonResponse({'message': 'Method not allowed'}, status=405)


@csrf_exempt
@jwt_required
def get_invoice_count(request):
    """GET /invoices/count - Count invoices for user."""
    if request.method != 'GET':
        return JsonResponse({'message': 'Method not allowed'}, status=405)

    search_query = request.GET.get('searchQuery', '')
    invoices = get_collection('invoices')

    if search_query:
        query = {'creator': search_query}
    else:
        query = {'creator': request.user_id}

    total_count = invoices.count_documents(query)
    return JsonResponse({'totalCount': total_count})


@csrf_exempt
@jwt_required
@require_http_methods(['GET', 'PATCH', 'DELETE'])
def invoice_detail(request, pk):
    """GET/PATCH/DELETE /invoices/{id}"""
    invoices = get_collection('invoices')

    try:
        oid = ObjectId(pk)
    except Exception:
        return JsonResponse({'message': f'Invalid id: {pk}'}, status=400)

    if request.method == 'GET':
        invoice = invoices.find_one({'_id': oid})
        if not invoice:
            return JsonResponse({'message': f'Invoice not found with id: {pk}'}, status=404)
        return JsonResponse(_invoice_to_dict(invoice))

    elif request.method == 'PATCH':
        body = json.loads(request.body)
        update_fields = {}

        updatable = [
            'dueDate', 'currency', 'items', 'rates', 'vat', 'total',
            'subTotal', 'notes', 'status', 'invoiceNumber', 'type',
            'creator', 'totalAmountReceived', 'client', 'paymentRecords',
        ]

        for field in updatable:
            if field in body and body[field] is not None:
                update_fields[field] = body[field]

        if not update_fields:
            return JsonResponse({'message': 'No fields to update'}, status=400)

        result = invoices.find_one_and_update(
            {'_id': oid},
            {'$set': update_fields},
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            return JsonResponse({'message': f'Invoice not found with id: {pk}'}, status=404)
        return JsonResponse(_invoice_to_dict(result))

    elif request.method == 'DELETE':
        result = invoices.delete_one({'_id': oid})
        if result.deleted_count == 0:
            return JsonResponse({'message': f'Invoice not found with id: {pk}'}, status=404)
        return JsonResponse({'message': 'Invoice deleted successfully'})
