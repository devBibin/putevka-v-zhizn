from .models import UserNotification

def unread_notifications(request):
    unread_count = 0
    if request.user.is_authenticated:
        unread_count = UserNotification.objects.filter(recipient=request.user, is_seen=False).count()
    return {'unread_notifications_count': unread_count}