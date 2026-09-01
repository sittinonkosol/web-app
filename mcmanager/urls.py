from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='mc_dashboard'),
    path('api/status', views.api_server_status, name='api_mc_status'),
    path('api/action', views.api_server_action, name='api_mc_action'),
    path('api/config', views.api_server_config, name='api_mc_config'),
    path('api/rcon', views.api_send_rcon, name='api_mc_rcon'),
]
