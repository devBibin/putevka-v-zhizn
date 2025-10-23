from django.contrib import admin

from review_by_tutor.models import Interview, TestAssignment


@admin.register(Interview)
class InterviewNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("notes", "user__username", "author__username")


@admin.register(TestAssignment)
class TestAssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "status", "assigned_by", "assigned_at", "due_at", "passed", "result_score")
    list_filter = ("status", "passed")
    search_fields = ("title", "user__username", "user__first_name", "user__last_name")
    autocomplete_fields = ("user", "assigned_by", "result_filled_by")
    readonly_fields = ("assigned_at", "result_filled_at", "completed_at")
