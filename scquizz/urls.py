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

    # Messages API
    path('api/messages', views.messages_view, name='messages_api'),
    path('api/messages/ws', views.ws_probe, name='ws_probe'),
    path('api/messages/<str:msg_id>/answer', views.answer_message, name='answer_message'),
    path('api/messages/<str:msg_id>/tts', views.message_tts, name='message_tts'),
    path('api/messages/<str:msg_id>', views.delete_message, name='delete_message'),

    # Polls API
    path('api/polls', views.polls_view, name='polls_api'),
    path('api/polls/events', views.poll_events_sse, name='poll_events_sse'),
    path('api/polls/active', views.active_poll_view, name='active_poll'),
    path('api/polls/<str:poll_id>/activate', views.activate_poll, name='activate_poll'),
    path('api/polls/<str:poll_id>/deactivate', views.deactivate_poll, name='deactivate_poll'),
    path('api/polls/<str:poll_id>/vote', views.vote_poll, name='vote_poll'),
    path('api/polls/<str:poll_id>', views.delete_poll, name='delete_poll'),

    # Static Assets serving
    re_path(r'^css/(?P<path>.*)$', serve, {'document_root': settings.BASE_DIR / 'scquizz' / 'template' / 'css'}),
    re_path(r'^js/(?P<path>.*)$', serve, {'document_root': settings.BASE_DIR / 'scquizz' / 'template' / 'js'}),
    re_path(r'^asset/(?P<path>.*)$', serve, {'document_root': settings.BASE_DIR / 'scquizz' / 'template' / 'asset'}),
]
