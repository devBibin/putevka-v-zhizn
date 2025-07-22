from django.db import models
from django.db import models
from django.contrib.auth.models import User

class TelegramAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='telegram_account')
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=150, blank=True, null=True)
    first_name = models.CharField(max_length=150, blank=True, null=True)
    last_name = models.CharField(max_length=150, blank=True, null=True)
    language_code = models.CharField(max_length=10, blank=True, null=True)
    is_bot = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)

    def __str__(self):
        return f"@{self.username or self.telegram_id}"

# Create your models here.
