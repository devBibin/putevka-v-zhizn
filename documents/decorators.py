import time
from functools import wraps

from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect


def rate_limit_uploads(rate_limit_seconds=60, max_uploads=5):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.method == 'POST':
                user_id = request.user.id
                cache_key = f'upload_rate_limit_{user_id}'

                timestamps = cache.get(cache_key, [])

                current_time = time.time()
                timestamps = [t for t in timestamps if current_time - t < rate_limit_seconds]

                if len(timestamps) >= max_uploads:
                    messages.error(request,
                                   f'Вы можете загружать не более {max_uploads} документов каждые {rate_limit_seconds} секунд.')
                    return redirect('documents_dashboard')

                timestamps.append(current_time)
                cache.set(cache_key, timestamps, timeout=rate_limit_seconds)

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
