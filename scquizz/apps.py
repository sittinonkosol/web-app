from django.apps import AppConfig

class ScquizzConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scquizz'
    verbose_name = 'SC Quiz & Polling'
    
    # Landing page metadata
    landing_url = '/scquizz/'
    landing_icon = '📊'
    landing_description = 'Interactive real-time messaging, Q&A, and live polling for events and classes.'
