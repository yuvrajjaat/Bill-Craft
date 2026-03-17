from django.urls import path
from . import views

urlpatterns = [
    path('/count', views.get_invoice_count),
    path('', views.invoice_list),
    path('/<str:pk>', views.invoice_detail),
]
