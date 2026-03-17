from django.urls import path
from . import views

urlpatterns = [
    path('/user', views.get_clients_by_user),
    path('/all', views.get_clients_paginated),
    path('', views.create_client),
    path('/<str:pk>', views.client_detail),
]
