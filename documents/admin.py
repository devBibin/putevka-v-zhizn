from django.contrib import admin
from .models import Document
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('caption', 'user', 'uploaded_at', 'get_file_url')
    list_filter = ('uploaded_at', 'user')
    search_fields = ('caption', 'user__username')
    date_hierarchy = 'uploaded_at'

    def get_file_url(self, obj):
        if obj.file:
            return admin.display(description="Файл", ordering="file")(lambda x: f'<a href="{x.file.url}" target="_blank">{x.file.name.split("/")[-1]}</a>')(obj)
        return "Нет файла"
    get_file_url.allow_tags = True


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 0
    fields = ('caption', 'file', 'uploaded_at')
    readonly_fields = ('uploaded_at',)

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.can_delete = False
        return formset

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True

class CustomUserAdmin(UserAdmin):
    inlines = [DocumentInline,]

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)