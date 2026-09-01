from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='mc_dashboard'),
    path('api/status', views.api_server_status, name='api_mc_status'),
    path('api/action', views.api_server_action, name='api_mc_action'),
    path('api/config', views.api_server_config, name='api_mc_config'),
    path('api/rcon', views.api_send_rcon, name='api_mc_rcon'),
    
    # Advanced Features
    path('api/players', views.api_players, name='api_mc_players'),
    path('api/player/entity-data', views.api_player_entity_data, name='api_mc_player_entity_data'),
    path('api/files', views.api_files, name='api_mc_files'),
    path('api/backups', views.api_backups, name='api_mc_backups'),
    path('api/backups/download/<str:filename>', views.api_download_backup, name='api_mc_download_backup'),
    path('api/logs/download', views.api_download_log, name='api_mc_download_log'),
    path('api/logs/clear', views.api_clear_log, name='api_mc_clear_log'),
    path('items/<str:item_name>.png', views.api_item_icon, name='mc_item_icon'),
]
