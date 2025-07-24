import logging

from Putevka.utils.middlewares import get_current_request


class UserInfoFilter(logging.Filter):
    def filter(self, record):
        try:
            request = get_current_request()
            if request and hasattr(request, 'user') and request.user.is_authenticated:
                record.username = request.user.username
                record.user_id = request.user.id
            else:
                record.username = 'anonymous'
                record.user_id = 'N/A'
        except Exception:
            record.username = 'system'
            record.user_id = 'N/A'
        return True
