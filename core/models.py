from django.contrib.auth.models import User
from django.db import models

class TelegramAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='telegram_account')
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=255, blank=True, null=True)
    first_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)
    secret_code = models.CharField(max_length=64, unique=True)  # для привязки
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} <-> @{self.username}"

# Create your models here.