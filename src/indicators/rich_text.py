from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import wagtail.admin.rich_text.editors.draftail.features as draftail_features
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.rich_text.converters import editor_html
from wagtail.admin.rich_text.converters.html_to_contentstate import LinkElementHandler
from wagtail.documents.rich_text import LinkHandler

from draftjs_exporter.dom import DOM

from indicators.models.indicator import Indicator

if TYPE_CHECKING:
    from collections.abc import Generator

    from indicators.models import Indicator


def indicator_link_entity(props):
    """
    Construct elements from contentstate data.

    Of form:
    <a id="1" linktype="indicator">indicator link</a>
    """

    return DOM.create_element(
        'a',
        {
            'linktype': 'indicator',
            'id': props.get('id'),
            'uuid': props.get('uuid'),
        },
        props['children'],
    )


class IndicatorLinkElementHandler(LinkElementHandler):
    """Convert database representation to contentstate."""

    def get_attribute_data(self, attrs):
        from .models import Indicator

        try:
            uuid = UUID(attrs['uuid'])
        except KeyError, ValueError:
            return {}
        id = attrs['id']
        try:
            indicator = Indicator.objects.get(uuid=uuid)
        except Indicator.DoesNotExist:
            return {'uuid': uuid, 'id': id}

        return {
            'id': indicator.id,
            'uuid': str(indicator.uuid),
            'edit_url': reverse('indicators_indicator_modeladmin_edit', args=[indicator.id]),
            'name': indicator.name,
        }


ContentstateIndicatorLinkConversionRule = {
    'from_database_format': {
        'a[linktype="indicator"]': IndicatorLinkElementHandler('INDICATOR'),
    },
    'to_database_format': {'entity_decorators': {'INDICATOR': indicator_link_entity}},
}


class IndicatorLinkHandlerEditor:
    @staticmethod
    def get_db_attributes(tag) -> dict[str, Any]:
        return {'uuid': tag['data-uuid'], 'id': tag['data-id']}

    @staticmethod
    def expand_db_attributes(attrs) -> str:
        from .models import Indicator

        try:
            indicator = Indicator.objects.get(uuid=UUID(attrs['uuid']))
            return '<a data-linktype="indicator" data-uuid="%s" data-id="%s">' % (
                str(indicator.uuid),
                indicator.id,
            )
        except Indicator.DoesNotExist:
            # Preserve the UUID attribute for troubleshooting purposes, even though it
            # points to a missing indicator
            return '<a data-linktype="indicator" data-uuid="%s" data-id="%s">' % (attrs['uuid'], attrs['id'])
        except KeyError:
            return '<a data-linktype="indicator">'


EditorHTMLIndicatorLinkConversionRule = [
    editor_html.LinkTypeRule('indicator', IndicatorLinkHandlerEditor),
]


class IndicatorLinkHandler(LinkHandler):
    identifier = 'indicator'

    @staticmethod
    def get_model() -> type[Indicator]:
        from .models import Indicator

        return Indicator

    @classmethod
    def expand_db_attributes(cls, attrs: dict[str, Any]) -> str:
        return cls.expand_db_attributes_many([attrs])[0]

    @classmethod
    def expand_one(cls, indicator: Indicator) -> str:
        return '<a href="/indicators/%d" data-link-type="indicator" data-id="%d" data-uuid="%s">' % (
            indicator.id,
            indicator.id,
            str(indicator.uuid),
        )

    @classmethod
    def expand_db_attributes_many(cls, attrs_list: list[dict[str, Any]]) -> list[str]:
        indicators = cast('list[Indicator]', cls.get_many(attrs_list))
        ret = [cls.expand_one(indicator) if indicator else '<a>' for indicator in indicators]
        return ret

    @classmethod
    def extract_references(cls, attrs) -> Generator[tuple[type[Indicator], int, str, str]]:
        # Yields tuples of (content_type_id, object_id, model_path, content_path)
        yield cls.get_model(), attrs['id'], '', ''


@hooks.register('register_rich_text_features')
def register_indicator_feature(features):
    features.register_link_type(IndicatorLinkHandler)

    link_feature = draftail_features.EntityFeature(
        {
            'type': 'INDICATOR',
            'icon': 'kausal-indicator',
            'description': _('Indicator'),
            'chooserUrls': {
                'indicatorChooser': reverse_lazy('indicator_chooser:choose'),
            },
        },
        js=['wagtailadmin/js/chooser-modal.js', 'indicators/js/indicator-entity.js'],
    )
    features.register_editor_plugin(
        'draftail',
        'indicator-link',
        link_feature,
    )

    features.register_converter_rule('editorhtml', 'indicator-link', EditorHTMLIndicatorLinkConversionRule)
    features.register_converter_rule('contentstate', 'indicator-link', ContentstateIndicatorLinkConversionRule)

    features.default_features.append('indicator-link')
