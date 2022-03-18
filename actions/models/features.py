from django.utils.translation import gettext_lazy as _
from django.db import models


class PlanFeatures(models.Model):
    plan = models.OneToOneField('actions.Plan', related_name='features', on_delete=models.CASCADE)
    allow_images_for_actions = models.BooleanField(
        default=True, verbose_name=_('allow images for actions'),
        help_text=_('Should custom images for individual actions be allowed')
    )
    show_admin_link = models.BooleanField(
        default=False, verbose_name=_('show admin link'),
        help_text=_('Should the public website contain a link to the admin login?'),
    )
    public_contact_persons = models.BooleanField(
        default=True, verbose_name=_('Contact persons private'),
        help_text=_('Set if the contact persons should be visible in the public UI')
    )
    has_action_identifiers = models.BooleanField(
        default=True, verbose_name=_('Hide action identifiers'),
        help_text=_("Set if the plan uses meaningful action identifiers")
    )
    has_action_official_name = models.BooleanField(
        default=False, verbose_name=_('Hide official name field'),
        help_text=_("Set if the plan uses the official name field")
    )
    has_action_lead_paragraph = models.BooleanField(
        default=True, verbose_name=_('Hide lead paragraph'),
        help_text=_("Set if the plan uses the lead paragraph field")
    )
    has_action_primary_orgs = models.BooleanField(
        default=False, verbose_name=_('Has primary organisations for actions'),
        help_text=_("Set if actions have a clear primary organisation (such as multi-city plans)")
    )
    enable_search = models.BooleanField(
        null=True, default=True, verbose_name=_('Enable site search'),
        help_text=_("Enable site-wide search functionality")
    )

    public_fields = [
        'allow_images_for_actions', 'show_admin_link', 'public_contact_persons',
        'has_action_identifiers', 'has_action_official_name', 'has_action_lead_paragraph',
        'has_action_primary_orgs', 'enable_search',
    ]

    class Meta:
        verbose_name = _('plan feature')
        verbose_name_plural = _('plan features')

    def __str__(self):
        return "Features for %s" % self.plan
