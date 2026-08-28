from django.urls import path, re_path
from django.views.static import serve
from django.conf import settings
from . import views

urlpatterns = [
    # Web Pages
    path('', views.index_view, name='index'),
    path('index.html', views.index_view, name='index_html'),
    path('login', views.login_view, name='login'),
    path('login.html', views.login_view, name='login_html'),
    path('admin', views.admin_view, name='admin'),
    path('admin.html', views.admin_view, name='admin_html'),

    # Locations REST API
    path('api/locations', views.locations_api, name='locations_api'),
    path('api/locations/<str:loc_id>', views.delete_location_api, name='delete_location_api'),

    # Static Assets serving
    re_path(r'^css/(?P<path>.*)$', serve, {'document_root': settings.BASE_DIR / 'map_locator' / 'template' / 'css'}),
    re_path(r'^js/(?P<path>.*)$', serve, {'document_root': settings.BASE_DIR / 'map_locator' / 'template' / 'js'}),
]
