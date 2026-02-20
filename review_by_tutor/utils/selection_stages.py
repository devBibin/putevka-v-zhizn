from functools import wraps

from django.shortcuts import redirect
from django.contrib import messages
from scholar_form.models import UserInfo


STEP_ORDER = [
    UserInfo.SelectionStep.FORM,
    UserInfo.SelectionStep.TEST,
    UserInfo.SelectionStep.ML,
    UserInfo.SelectionStep.VIDEO,
    UserInfo.SelectionStep.INTERVIEW_PREP,
]


def step_index(step: str) -> int:
    return STEP_ORDER.index(step)


def can_access_step(uinfo: UserInfo, step: str) -> bool:
    if not uinfo.selection_step:
        return False
    return step_index(step) <= step_index(uinfo.selection_step)


def require_selection_step(required_step):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            uinfo, _ = UserInfo.objects.get_or_create(user=request.user)

            if required_step and not can_access_step(uinfo, required_step):
                messages.warning(request, "Сначала завершите предыдущий этап.")
                return redirect("form_step_entry")

            return view_func(request, *args, **kwargs)

        return _wrapped_view
    return decorator