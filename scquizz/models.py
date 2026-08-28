from django.db import models

class Message(models.Model):
    id = models.CharField(max_length=64, primary_key=True)
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
