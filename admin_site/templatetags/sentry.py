from django import template
from admin_site.context_processors import sentry as sentry_context
from actions.context_processors import current_plan

register = template.Library()

# Will be toggled externally
sentry_bundle_installed = False


@register.inclusion_tag('admin_site/sentry_js.html', takes_context=True)
def sentry_js(context: dict):
    req = context.get('request')
    sentry_ctx = sentry_context(req)
    return sentry_ctx | dict(sentry_bundle_installed=sentry_bundle_installed, request=req)


@register.inclusion_tag('admin_site/sentry_init.html', takes_context=True)
def sentry_init(context: dict, flush_replay: bool = False, event_id: int | None = None):
    req = context.get('request')
    ctx = dict(
        sentry_flush_replay=flush_replay,
        sentry_bundle_installed=sentry_bundle_installed,
        sentry_error_id=event_id,
        request=req,
    )
    ctx |= sentry_context(req)
    if req is not None:
        ctx |= current_plan(req)
    return ctx
