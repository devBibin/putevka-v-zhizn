from django.db import models
from django.utils import timezone
import uuid

class EmailSubscriber(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    invited_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.email
