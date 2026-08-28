from django.db import models
from django.contrib.auth.models import User, Group

class AppSetting(models.Model):
    app_name = models.CharField(max_length=100, primary_key=True)
    display_name = models.CharField(max_length=200, blank=True)
    icon = models.CharField(max_length=50, default='🚀')
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=True, help_text="True if accessible without login")
    min_role_required = models.CharField(
        max_length=50,
        default='viewer',
        choices=[
            ('viewer', 'Viewer (เข้าชมได้)'),
            ('moderator', 'Moderator (จัดการข้อมูล)'),
            ('admin', 'Admin (ผู้ดูแลแอปเต็มรูปแบบ)'),
        ]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_app_settings'
        verbose_name = 'App Setting'
        verbose_name_plural = 'App Settings'

    def __str__(self):
        return f"{self.display_name or self.app_name} (Public: {self.is_public})"

class UserAppPermission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='app_permissions')
    app_name = models.CharField(max_length=100)
    role = models.CharField(
        max_length=50,
        default='viewer',
        choices=[
            ('none', 'No Access (ไม่มีสิทธิ์)'),
            ('viewer', 'Viewer (ดูข้อมูล/เล่นแอป)'),
            ('moderator', 'Moderator (จัดการข้อมูลในแอป)'),
            ('admin', 'Admin (ผู้ดูแลแอป)'),
        ]
    )

    class Meta:
        db_table = 'core_user_app_permissions'
        unique_together = ('user', 'app_name')

    def __str__(self):
        return f"{self.user.username} -> {self.app_name}: {self.role}"

class GroupAppPermission(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='app_permissions')
    app_name = models.CharField(max_length=100)
    role = models.CharField(
        max_length=50,
        default='viewer',
        choices=[
            ('none', 'No Access (ไม่มีสิทธิ์)'),
            ('viewer', 'Viewer (ดูข้อมูล/เล่นแอป)'),
            ('moderator', 'Moderator (จัดการข้อมูลในแอป)'),
            ('admin', 'Admin (ผู้ดูแลแอป)'),
        ]
    )

    class Meta:
        db_table = 'core_group_app_permissions'
        unique_together = ('group', 'app_name')

    def __str__(self):
        return f"{self.group.name} -> {self.app_name}: {self.role}"

class UserLoginLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='login_logs')
    username_attempted = models.CharField(max_length=150)
    ip_address = models.CharField(max_length=64, blank=True, default='')
    user_agent = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'เข้าสู่ระบบสำเร็จ'),
            ('failed', 'เข้าสู่ระบบไม่สำเร็จ'),
        ],
        default='success'
    )
    failure_reason = models.CharField(max_length=255, blank=True, default='')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_user_login_logs'
        ordering = ['-timestamp']
        verbose_name = 'User Login Log'
        verbose_name_plural = 'User Login Logs'

    def __str__(self):
        return f"{self.username_attempted} [{self.status}] at {self.timestamp}"

