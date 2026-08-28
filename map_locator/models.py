import uuid
from django.db import models

class LocationMarker(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, verbose_name="ชื่อสถานที่ / จุดปักหมุด")
    category = models.CharField(max_length=100, default="ทั่วไป", verbose_name="หมวดหมู่")
    description = models.TextField(blank=True, default="", verbose_name="รายละเอียด")
    latitude = models.FloatField(verbose_name="ละติจูด (Latitude)")
    longitude = models.FloatField(verbose_name="ลองจิจูด (Longitude)")
    address = models.CharField(max_length=500, blank=True, default="", verbose_name="ที่อยู่ / บริเวณใกล้เคียง")
    created_by = models.CharField(max_length=150, default="ผู้ใช้ทั่วไป", verbose_name="ผู้บันทึก")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="เวลาที่บันทึก")

    class Meta:
        db_table = 'location_markers'
        ordering = ['-created_at']
        verbose_name = "Location Marker"
        verbose_name_plural = "Location Markers"

    def __str__(self):
        return f"{self.title} ({self.latitude:.4f}, {self.longitude:.4f})"
