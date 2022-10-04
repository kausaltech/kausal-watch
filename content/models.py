import reversion
from django.db import models
from django.utils.translation import gettext_lazy as _
from modeltrans.fields import TranslationField


@reversion.register()
class SiteGeneralContent(models.Model):
    class ActionTerm(models.TextChoices):
        # When changing terms, make sure to also change ACTION_TERM_PLURAL below.
        # Get a printable SiteGeneralContent instance's action term with `instance.get_action_term_display()` and, for
        # plural, `instance.get_action_term_display_plural()`.
        ACTION = 'action', _('Action')
        STRATEGY = 'strategy', _('Strategy')

    ACTION_TERM_PLURAL = {
        ActionTerm.ACTION: _('Actions'),
        ActionTerm.STRATEGY: _('Strategies'),
    }

    plan = models.OneToOneField(
        'actions.Plan', related_name='general_content', verbose_name=_('plan'), on_delete=models.CASCADE,
        unique=True
    )
    site_title = models.CharField(max_length=150, verbose_name=_('site title'), blank=True)
    site_description = models.CharField(max_length=150, verbose_name=_('site description'), blank=True)
    owner_url = models.URLField(blank=True, verbose_name=_('URL for the owner of the site'))
    owner_name = models.CharField(blank=True, max_length=150, verbose_name=_('Name of the owner of the site'))

    official_name_description = models.CharField(
        max_length=200, verbose_name=_('official name description'),
        help_text=_('The text to show when displaying official content'),
        blank=True,
    )
    copyright_text = models.CharField(max_length=150, verbose_name=_('copyright text'), blank=True)
    creative_commons_license = models.CharField(
        blank=True, max_length=150, default='CC BY 4.0', verbose_name=_('creative commons license'),
        help_text=_('If the site is under a Creative Commons license, which CC license it is'),
    )
    github_api_repository = models.URLField(blank=True, verbose_name=_('Link to GitHub repository for API'))
    github_ui_repository = models.URLField(blank=True, verbose_name=_('Link to GitHub repository for UI'))
    action_term = models.CharField(
        max_length=30, choices=ActionTerm.choices, verbose_name=_("Term to use for 'action'"), default=ActionTerm.ACTION
    )

    i18n = TranslationField(
        fields=[
            'site_title', 'site_description', 'official_name_description', 'copyright_text',
            'creative_commons_license', 'owner_name', 'owner_url'
        ],
        default_language_field='plan__primary_language')

    public_fields = [
        'id', 'site_title', 'site_description', 'owner_url', 'owner_name', 'official_name_description',
        'copyright_text', 'creative_commons_license', 'github_api_repository', 'github_ui_repository', 'action_term',
    ]

    class Meta:
        verbose_name = _('site general content')
        verbose_name_plural = _('site general contents')

    def __str__(self):
        if self.plan:
            return str(self.plan)
        else:
            return '[unknown]'

    def get_action_term_display_plural(self):
        # Analogous to get_action_term_display, which Django automatically generates
        return SiteGeneralContent.ACTION_TERM_PLURAL[SiteGeneralContent.ActionTerm(self.action_term)]
