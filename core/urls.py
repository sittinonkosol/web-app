from django.urls import path, include
from . import views

urlpatterns = [
    path('robots.txt', views.robots_txt, name='robots_txt'),

    path('', views.landing_page, name='landing'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('profile/', views.profile_view, name='profile'),

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
    path('api/admin/registrations/pending', views.api_pending_registrations, name='api_admin_pending_registrations'),
    path('api/admin/registrations/<int:user_id>/approve', views.api_approve_registration, name='api_admin_approve_registration'),
    path('api/admin/registrations/<int:user_id>/reject', views.api_reject_registration, name='api_admin_reject_registration'),

    # Apps
    path('ict/scquizz/', include('scquizz.urls')),
    path('mc/', include('mcmanager.urls')),
]
