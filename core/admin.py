from django.contrib import admin

from core.models import MotivationLetter


@admin.register(MotivationLetter)
class MotivationLetterAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at', 'admin_rating', 'gpt_review')
    list_filter = ('created_at',)
    search_fields = ('letter_text', 'user__username')

    fields = ('user', 'letter_text', 'admin_rating', 'gpt_review', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')
