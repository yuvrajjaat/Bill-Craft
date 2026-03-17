from django.urls import path
from . import views

urlpatterns = [
    path('send-pdf', views.send_pdf),
    path('create-pdf', views.create_pdf),
    path('fetch-pdf', views.fetch_pdf),
    path('public/pdf/<str:pk>', views.public_pdf),
]
