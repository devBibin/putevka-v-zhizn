from django.contrib.auth.models import User
from django.db import models

class TelegramAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=255, blank=True, null=True)
    first_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.username or str(self.telegram_id)

# Create your models here.