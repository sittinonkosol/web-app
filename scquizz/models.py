from django.db import models
import uuid

class QuizSession(models.Model):
    id = models.CharField(max_length=64, primary_key=True, default=uuid.uuid4)
    title = models.CharField(max_length=255, default='General Session')
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'quiz_sessions'
        ordering = ['-created_at']

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.title} ({status})"

class Message(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    session = models.ForeignKey(QuizSession, on_delete=models.CASCADE, null=True, blank=True, related_name='messages')
    name = models.CharField(max_length=255)
    text = models.TextField()
    ts = models.BigIntegerField()
    answered = models.IntegerField(default=0)

    class Meta:
        db_table = 'messages'
        ordering = ['ts']

    def __str__(self):
        return f"{self.name}: {self.text[:30]}"

class Poll(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
    session = models.ForeignKey(QuizSession, on_delete=models.CASCADE, null=True, blank=True, related_name='polls')
    question = models.TextField()
    options = models.JSONField(default=list)
    votes = models.JSONField(default=list)
    active = models.IntegerField(default=0)
    type = models.CharField(max_length=50, default='standard')
    scope = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'polls'

    def __str__(self):
        return f"{self.question} (Active: {self.active})"

