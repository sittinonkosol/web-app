from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('ict/scquizz/', include('scquizz.urls')),
    path('map-locator/', include('map_locator.urls')),
]
