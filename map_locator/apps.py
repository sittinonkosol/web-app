from django.apps import AppConfig

class MapLocatorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'map_locator'
    verbose_name = 'Map Locator'
    landing_icon = '🗺️'
    landing_description = 'ระบบระบุและบันทึกพิกัดตำแหน่งบนแผนที่ OpenStreetMap แบบเรียลไทม์'
