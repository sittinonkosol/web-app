from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Central Admin Dashboard
    path('admin/', views.admin_dashboard_view, name='admin_dashboard'),
    
    # Central Admin APIs
    path('api/admin/users', views.api_users_list_create, name='api_admin_users'),
    path('api/admin/users/<int:user_id>', views.api_user_detail, name='api_admin_user_detail'),
    path('api/admin/groups', views.api_groups_list_create, name='api_admin_groups'),
    path('api/admin/groups/<int:group_id>', views.api_group_detail, name='api_admin_group_detail'),
    path('api/admin/app-settings', views.api_app_settings_list, name='api_admin_app_settings'),
    path('api/admin/app-settings/<str:app_name>', views.api_app_setting_detail, name='api_admin_app_setting_detail'),
    path('api/admin/login-logs', views.api_login_logs_list, name='api_admin_login_logs'),
    path('api/admin/users/<int:user_id>/login-logs', views.api_user_login_logs, name='api_admin_user_login_logs'),

    # Apps
    path('ict/scquizz/', include('scquizz.urls')),
]
