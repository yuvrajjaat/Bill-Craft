from django.urls import path
from . import views

urlpatterns = [
    path('', views.profile_list),
    path('/<str:pk>', views.profile_detail),
]
