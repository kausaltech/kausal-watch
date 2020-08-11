from django.db import models
from django.utils.translation import gettext_lazy as _
from modeltrans.fields import TranslationField
from wagtail.admin.edit_handlers import FieldPanel, StreamFieldPanel
from wagtail.core.models import Page
from wagtail.core.fields import StreamField
from wagtail.core import blocks


class AplansPage(Page):
    i18n = TranslationField(fields=('title', 'slug', 'url_path'))

    class Meta:
        abstract = True


class PlanRootPage(AplansPage):
    parent_page_types = []
    subpage_types = ['pages.StaticPage']


class StaticPage(AplansPage):
    body = StreamField([
        ('heading', blocks.CharBlock(classname='full title')),
        ('paragraph', blocks.RichTextBlock()),
    ])

    content_panels = Page.content_panels + [
        StreamFieldPanel('body'),
    ]
