from django.db import models
from django.contrib.auth.models import User

class Document(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='documents/')
    caption = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s document: {self.caption or self.file.name}"