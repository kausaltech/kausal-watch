from django.utils.translation import ugettext_lazy as _

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
        'required': True,
    }, {
        'identifier': 'completed',
        'name': _("Completed"),
        'required': True,
    }
]
