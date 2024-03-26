from django.utils.translation import gettext_lazy as _

DEFAULT_ACTION_STATUSES = [
    {
        'identifier': 'on_time',
        'name': _("On time"),
    }, {
        'identifier': 'late',
        'name': _("Late"),
    }, {
        'identifier': 'cancelled',
        'name': _("Cancelled or postponed"),
        'is_completed': True,
    },
]

DEFAULT_ACTION_IMPLEMENTATION_PHASES = [
    {
        'identifier': 'not_started',
        'name': _("Not started"),
    }, {
        'identifier': 'planning',
        'name': _("Planning"),
    }, {
        'identifier': 'implementation',
        'name': _("Implementation"),
    }, {
        'identifier': 'completed',
        'name': _("Completed"),
    }
]
