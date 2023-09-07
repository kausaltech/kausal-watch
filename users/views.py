from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.utils.http import (
    url_has_allowed_host_and_scheme, urlsafe_base64_decode,
)

@require_http_methods(['POST', 'GET'])
@login_required
def change_admin_plan(request, plan_id=None):
    user = request.user
    plans = user.get_adminable_plans()

    if request.method == 'POST':
        plan = request.POST.get('plan', None)
    else:
        plan = plan_id

    if plan is None:
        return HttpResponseBadRequest("No plan given")
    try:
        plan_id = int(plan)
    except ValueError:
        return HttpResponseBadRequest("Invalid plan id")

    for plan in plans:
        if plan.id == plan_id:
            break
    else:
        return HttpResponseBadRequest("Not allowed plan id")

    user = request.user
    user.selected_admin_plan = plan
    user.save(update_fields=['selected_admin_plan'])

    redirect_to = request.POST.get(
        REDIRECT_FIELD_NAME,
        request.GET.get(REDIRECT_FIELD_NAME, '')
    )
    if redirect_to:
        url_is_safe = url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts=[request.get_host()],
            require_https=request.is_secure(),
        )
        if url_is_safe:
            return HttpResponseRedirect(redirect_to)

    return HttpResponseRedirect(reverse('wagtailadmin_home'))
