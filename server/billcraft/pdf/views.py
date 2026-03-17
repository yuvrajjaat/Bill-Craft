import json
import io
import tempfile
import os
from datetime import datetime

from bson import ObjectId
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.mail import EmailMessage
from django.conf import settings
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa
from pathlib import Path

# In-memory PDF cache (mimics the Java ConcurrentHashMap)
_pdf_cache = {}

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / 'templates'


def _get_jinja_env():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )


def _flatten_invoice_data(body):
    """Extract invoiceData and profileData fields to top level."""
    invoice_data = body.get('invoiceData', {})
    profile_data = body.get('profileData', {})

    # Merge invoice data to top level
    data = {}
    for key in ['invoiceNumber', 'type', 'status', 'currency', 'dueDate',
                 'createdAt', 'items', 'vat', 'total', 'subTotal', 'notes',
                 'totalAmountReceived', 'rates', 'client']:
        data[key] = invoice_data.get(key, body.get(key, ''))

    # Company info from profile
    data['companyName'] = profile_data.get('businessName', body.get('company', ''))
    data['companyEmail'] = profile_data.get('email', '')
    data['companyPhone'] = profile_data.get('phoneNumber', '')
    data['companyAddress'] = profile_data.get('contactAddress', '')
    data['companyWebsite'] = profile_data.get('website', '')

    # Additional fields
    data['email'] = body.get('email', '')
    data['company'] = body.get('company', '')
    data['balance'] = body.get('balance', 0)
    data['link'] = body.get('link', '')

    return data


def _generate_pdf_bytes(data):
    """Generate PDF bytes from invoice data using Jinja2 + xhtml2pdf."""
    env = _get_jinja_env()
    template = env.get_template('invoice-pdf.html')

    # Prepare template context
    client = data.get('client', {})
    items = data.get('items', [])
    total = float(data.get('total', 0) or 0)
    total_received = float(data.get('totalAmountReceived', 0) or 0)
    balance_due = total - total_received
    vat = float(data.get('vat', 0) or 0)
    sub_total = float(data.get('subTotal', 0) or 0)

    # Format dates
    due_date = data.get('dueDate', '')
    created_at = data.get('createdAt', '')
    try:
        if due_date and isinstance(due_date, str):
            due_date = datetime.fromisoformat(due_date.replace('Z', '+00:00')).strftime('%b %d, %Y')
    except (ValueError, TypeError):
        pass
    try:
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00')).strftime('%b %d, %Y')
    except (ValueError, TypeError):
        pass

    # Status color
    status = data.get('status', 'Unpaid')
    status_colors = {
        'Paid': '#4caf50',
        'Partial': '#ff9800',
        'Unpaid': '#f44336',
        'Overdue': '#d32f2f',
    }
    status_color = status_colors.get(status, '#9e9e9e')

    context = {
        'companyName': data.get('companyName', ''),
        'companyEmail': data.get('companyEmail', ''),
        'companyPhone': data.get('companyPhone', ''),
        'companyAddress': data.get('companyAddress', ''),
        'companyWebsite': data.get('companyWebsite', ''),
        'invoiceNumber': data.get('invoiceNumber', ''),
        'invoiceType': data.get('type', 'Invoice'),
        'status': status,
        'statusColor': status_color,
        'currency': data.get('currency', ''),
        'dueDate': due_date,
        'createdAt': created_at,
        'clientName': client.get('name', ''),
        'clientEmail': client.get('email', ''),
        'clientPhone': client.get('phone', ''),
        'clientAddress': client.get('address', ''),
        'items': items,
        'subTotal': f'{sub_total:,.2f}',
        'vat': vat,
        'vatAmount': f'{sub_total * vat / 100:,.2f}',
        'total': f'{total:,.2f}',
        'totalAmountReceived': f'{total_received:,.2f}',
        'balanceDue': f'{balance_due:,.2f}',
        'notes': data.get('notes', ''),
    }

    html_content = template.render(context)

    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.StringIO(html_content), dest=pdf_buffer)

    if pisa_status.err:
        return None

    return pdf_buffer.getvalue()


@csrf_exempt
@require_http_methods(['POST'])
def send_pdf(request):
    """POST /send-pdf - Generate PDF and send via email."""
    try:
        body = json.loads(request.body)
        recipient_email = body.get('email', '').strip()

        if not recipient_email:
            return JsonResponse({'message': 'Recipient email is required'}, status=400)

        data = _flatten_invoice_data(body)
        pdf_bytes = _generate_pdf_bytes(data)

        if pdf_bytes is None:
            return JsonResponse({'message': 'Failed to generate PDF'}, status=500)

        # Render email HTML
        env = _get_jinja_env()
        email_template = env.get_template('invoice-email.html')
        email_html = email_template.render(
            companyName=data.get('companyName', data.get('company', 'BillCraft')),
            invoiceNumber=data.get('invoiceNumber', ''),
            balance=f"{float(data.get('balance', 0)):,.2f}",
            currency=data.get('currency', ''),
            link=data.get('link', ''),
        )

        # Send email with attachment
        company_name = data.get('companyName', data.get('company', 'BillCraft'))
        email = EmailMessage(
            subject=f'Invoice from {company_name}',
            body=email_html,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
        )
        email.content_subtype = 'html'
        email.attach(
            f"invoice-{data.get('invoiceNumber', 'document')}.pdf",
            pdf_bytes,
            'application/pdf',
        )
        email.send(fail_silently=False)

        return JsonResponse({'message': 'Invoice sent successfully'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'message': f'Failed to send PDF: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(['POST'])
def create_pdf(request):
    """POST /create-pdf - Generate PDF and store in memory."""
    try:
        body = json.loads(request.body)
        data = _flatten_invoice_data(body)
        pdf_bytes = _generate_pdf_bytes(data)

        if pdf_bytes is None:
            return JsonResponse({'message': 'Failed to generate PDF'}, status=500)

        _pdf_cache['latest'] = pdf_bytes
        return JsonResponse({'message': 'PDF created successfully', 'key': 'latest'})

    except Exception as e:
        return JsonResponse({'message': f'Failed to create PDF: {str(e)}'}, status=500)


@require_http_methods(['GET'])
def fetch_pdf(request):
    """GET /fetch-pdf - Download the most recently generated PDF."""
    pdf_bytes = _pdf_cache.get('latest')
    if not pdf_bytes:
        return JsonResponse({'message': 'No PDF found. Create one first.'}, status=404)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="invoice.pdf"'
    return response


@require_http_methods(['GET'])
def public_pdf(request, pk):
    """GET /public/pdf/{id} - Public invoice PDF view."""
    try:
        from billcraft.db import get_collection

        invoices = get_collection('invoices')
        profiles = get_collection('profiles')

        try:
            oid = ObjectId(pk)
        except Exception:
            return JsonResponse({'message': f'Invalid id: {pk}'}, status=400)

        invoice = invoices.find_one({'_id': oid})
        if not invoice:
            return JsonResponse({'message': 'Invoice not found'}, status=404)

        # Get creator's profile
        creator_id = str(invoice.get('creator', ''))
        profile = profiles.find_one({'userId': creator_id})

        # Build data for PDF generation
        data = {
            'invoiceNumber': invoice.get('invoiceNumber', ''),
            'type': invoice.get('type', 'Invoice'),
            'status': invoice.get('status', 'Unpaid'),
            'currency': invoice.get('currency', ''),
            'dueDate': invoice.get('dueDate', ''),
            'createdAt': invoice.get('createdAt', ''),
            'client': invoice.get('client', {}),
            'items': invoice.get('items', []),
            'subTotal': invoice.get('subTotal', 0),
            'vat': invoice.get('vat', 0),
            'total': invoice.get('total', 0),
            'totalAmountReceived': invoice.get('totalAmountReceived', 0),
            'notes': invoice.get('notes', ''),
            'rates': invoice.get('rates', ''),
        }

        if profile:
            data['companyName'] = profile.get('businessName', '')
            data['companyEmail'] = profile.get('email', '')
            data['companyPhone'] = profile.get('phoneNumber', '')
            data['companyAddress'] = profile.get('contactAddress', '')
            data['companyWebsite'] = profile.get('website', '')
        else:
            data['companyName'] = ''
            data['companyEmail'] = ''
            data['companyPhone'] = ''
            data['companyAddress'] = ''
            data['companyWebsite'] = ''

        # Handle datetime objects from MongoDB
        for field in ['dueDate', 'createdAt']:
            val = data.get(field)
            if isinstance(val, datetime):
                data[field] = val.isoformat()

        pdf_bytes = _generate_pdf_bytes(data)
        if pdf_bytes is None:
            return JsonResponse({'message': 'Failed to generate PDF'}, status=500)

        inv_number = invoice.get('invoiceNumber', 'invoice')
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="invoice-{inv_number}.pdf"'
        return response

    except Exception as e:
        return JsonResponse({'message': f'Failed to generate PDF: {str(e)}'}, status=500)
