from django.utils.translation import ugettext_lazy as _

DEFAULT_ACTION_IMPLEMENTATION_PHASES = [
    {
        'identifier': 'not_started',
        'name': _("Not started"),
        'required': False,
    }, {
        'identifier': 'planning',
        'name': _("Planning"),
        'required': False,
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

DEFAULT_ACTION_IMPLEMENTATION_PHASE_IDENTIFIERS = [
    p['identifier'] for p in DEFAULT_ACTION_IMPLEMENTATION_PHASES
]
