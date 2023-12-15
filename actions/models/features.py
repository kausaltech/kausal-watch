from typing import ClassVar
import reversion
from django.utils.translation import gettext_lazy as _
from django.db import models


@reversion.register()
class PlanFeatures(models.Model):
    class ContactPersonsPublicData(models.TextChoices):
        NONE = 'none', _('Do not show contact persons publicly')
        NAME = 'name', _('Show only name, role and affiliation')
        ALL = 'all', _('Show all information')

    plan = models.OneToOneField('actions.Plan', related_name='features', on_delete=models.CASCADE)
    allow_images_for_actions = models.BooleanField(
        default=True, verbose_name=_('Allow images for actions'),
        help_text=_('Should custom images for individual actions be allowed')
    )
    show_admin_link = models.BooleanField(
        default=False, verbose_name=_('Show admin link'),
        help_text=_('Should the public website contain a link to the admin login?'),
    )
    contact_persons_public_data = models.CharField(
        max_length=50,
        choices=ContactPersonsPublicData.choices,
        default=ContactPersonsPublicData.ALL,
        verbose_name=_('Publicly visible data about contact persons'),
        help_text=_('Choose which information about contact persons is visible in the public UI')
    )
    has_action_identifiers = models.BooleanField(
        default=True, verbose_name=_('Has action identifiers'),
        help_text=_("Set if the plan uses meaningful action identifiers")
    )
    show_action_identifiers = models.BooleanField(
        default=True, verbose_name=_('Show action identifiers'),
        help_text=_("Set if action identifiers should be visible in the public UI")
    )
    has_action_contact_person_roles = models.BooleanField(
        default=False, verbose_name=_('Action contact persons have different roles'),
        help_text=_("Set if there are separate contact persons with publishing rights and others who can only suggest changes")
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
        default=False, verbose_name=_('Has primary organizations for actions'),
        help_text=_("Set if actions have a clear primary organization (such as multi-city plans)")
    )
    enable_search = models.BooleanField(
        default=True, verbose_name=_('Enable site search'),
        help_text=_("Enable site-wide search functionality")
    )
    enable_indicator_comparison = models.BooleanField(
        default=True, verbose_name=_('Enable indicator comparison'),
        help_text=_("Set to enable comparing indicators between organizations")
    )
    enable_moderation_workflow = models.BooleanField(
        default=False, verbose_name=_('Enable moderation workflow'),
        help_text=_("Set to enable drafting and reviewing functionality")
    )
    display_field_visibility_restrictions = models.BooleanField(
        default=False, verbose_name=_('Display field visibility as a label in edit views'),
        help_text=_(
            "For plans which have field-specific visibility restrictions, "
            "show to users which fields are public and which are restricted."
        )
    )

    @property
    def public_contact_persons(self):
        return self.contact_persons_public_data != self.ContactPersonsPublicData.NONE

    public_fields: ClassVar = [
        'allow_images_for_actions', 'show_admin_link', 'public_contact_persons', 'contact_persons_public_data',
        'has_action_identifiers', 'has_action_official_name', 'has_action_lead_paragraph',
        'has_action_primary_orgs', 'enable_search', 'enable_indicator_comparison',
        'minimal_statuses', 'has_action_contact_person_roles'
    ]

    class Meta:
        verbose_name = _('plan feature')
        verbose_name_plural = _('plan features')

    def __str__(self):
        return "Features for %s" % self.plan
