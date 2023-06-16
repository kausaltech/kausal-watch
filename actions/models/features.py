import reversion
from django.utils.translation import gettext_lazy as _
from django.db import models


@reversion.register()
class PlanFeatures(models.Model):
    plan = models.OneToOneField('actions.Plan', related_name='features', on_delete=models.CASCADE)
    allow_images_for_actions = models.BooleanField(
        default=True, verbose_name=_('Allow images for actions'),
        help_text=_('Should custom images for individual actions be allowed')
    )
    show_admin_link = models.BooleanField(
        default=False, verbose_name=_('Show admin link'),
        help_text=_('Should the public website contain a link to the admin login?'),
    )
    public_contact_persons = models.BooleanField(
        default=True, verbose_name=_('Contact persons public'),
        help_text=_('Set if the contact persons should be visible in the public UI')
    )
    has_action_identifiers = models.BooleanField(
        default=True, verbose_name=_('Has action identifiers'),
        help_text=_("Set if the plan uses meaningful action identifiers")
    )
    show_action_identifiers = models.BooleanField(
        default=True, verbose_name=_('Show action identifiers'),
        help_text=_("Set if action identifiers should be visible in the public UI")
    )
    minimal_statuses = models.BooleanField(
        default=False, verbose_name=_('Minimal statuses'),
        help_text=_(
            "Set to prevent showing status-specific graphs "
            "and other elements if statuses aren't systematically used in this action plan"
        )
    )
    has_action_official_name = models.BooleanField(
        default=False, verbose_name=_('Has action official name field'),
        help_text=_("Set if the plan uses the official name field")
    )
    has_action_lead_paragraph = models.BooleanField(
        default=True, verbose_name=_('Has action lead paragraph'),
        help_text=_("Set if the plan uses the lead paragraph field")
    )
    has_action_primary_orgs = models.BooleanField(
        default=False, verbose_name=_('Has primary organisations for actions'),
        help_text=_("Set if actions have a clear primary organisation (such as multi-city plans)")
    )
    enable_search = models.BooleanField(
        default=True, verbose_name=_('Enable site search'),
        help_text=_("Enable site-wide search functionality")
    )
    enable_indicator_comparison = models.BooleanField(
        default=True, verbose_name=_('Enable indicator comparison'),
        help_text=_("Set to enable comparing indicators between organizations")
    )

    public_fields = [
        'allow_images_for_actions', 'show_admin_link', 'public_contact_persons',
        'has_action_identifiers', 'has_action_official_name', 'has_action_lead_paragraph',
        'has_action_primary_orgs', 'enable_search', 'enable_indicator_comparison',
        'minimal_statuses'
    ]

    class Meta:
        verbose_name = _('plan feature')
        verbose_name_plural = _('plan features')

    def __str__(self):
        return "Features for %s" % self.plan
