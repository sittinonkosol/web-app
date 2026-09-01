from django.db import models
from django.utils.crypto import get_random_string

class ServerSetting(models.Model):
    server_path = models.CharField(max_length=255, default='/wdc/PaperMC')
    rcon_port = models.IntegerField(default=25575)
    rcon_password = models.CharField(max_length=128, blank=True)
    
    # Track assigned RAM
    max_ram_mb = models.IntegerField(default=4096, help_text="Allocated RAM in MB")
    
    def save(self, *args, **kwargs):
        if not self.rcon_password:
            self.rcon_password = get_random_string(32)
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        obj, created = cls.objects.get_or_create(id=1)
        return obj

    def __str__(self):
        return f"MC Server Settings ({self.server_path})"
