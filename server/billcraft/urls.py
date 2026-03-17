from django.urls import path, include

urlpatterns = [
    path('users/', include('billcraft.users.urls')),
    path('clients', include('billcraft.clients.urls')),
    path('invoices', include('billcraft.invoices.urls')),
    path('profiles', include('billcraft.profiles.urls')),
    path('', include('billcraft.pdf.urls')),
]
