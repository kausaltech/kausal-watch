from __future__ import annotations

import pytest

from images.rich_text import ImageEmbedHandler
from images.tests.factories import AplansImageFactory

pytestmark = pytest.mark.django_db


class TestImageEmbedHandlerCredit:
    """Tests for image credit injection in rich text image rendering."""

    def test_no_credit_attribute_when_empty(self):
        image = AplansImageFactory.create(image_credit='')
        result = ImageEmbedHandler.expand_db_attributes({
            'id': str(image.pk),
            'format': 'fullwidth',
            'alt': 'test',
        })
        assert 'data-image-credit' not in result

    def test_no_credit_attribute_when_blank(self):
        image = AplansImageFactory.create()
        result = ImageEmbedHandler.expand_db_attributes({
            'id': str(image.pk),
            'format': 'left',
            'alt': 'test',
        })
        assert 'data-image-credit' not in result

    def test_credit_html_escaped(self):
        image = AplansImageFactory.create(image_credit='Smith & Sons / "The Agency"')
        result = ImageEmbedHandler.expand_db_attributes({
            'id': str(image.pk),
            'format': 'fullwidth',
            'alt': 'test',
        })
        # The credit should be present but HTML-escaped by the img_tag renderer
        assert 'data-image-credit=' in result
        assert 'Smith &amp; Sons' in result
        assert '&quot;The Agency&quot;' in result

    def test_credit_works_with_all_builtin_formats(self):
        image = AplansImageFactory.create(image_credit='Credit')
        for fmt in ('fullwidth', 'left', 'right'):
            result = ImageEmbedHandler.expand_db_attributes({
                'id': str(image.pk),
                'format': fmt,
                'alt': 'test',
            })
            assert 'data-image-credit="Credit"' in result, f'Failed for format {fmt}'

    def test_credit_works_with_zoomable_format(self):
        image = AplansImageFactory.create(image_credit='Unsplash')
        result = ImageEmbedHandler.expand_db_attributes({
            'id': str(image.pk),
            'format': 'fullwidth-zoomable',
            'alt': 'test',
        })
        assert 'data-image-credit="Unsplash"' in result
        # Zoomable format should still add its own data attributes
        assert 'data-original-width=' in result


class TestImageEmbedHandlerExpandMany:
    """Tests for batch expansion of multiple images."""

    def test_multiple_images_with_different_credits(self):
        img1 = AplansImageFactory.create(image_credit='Credit A')
        img2 = AplansImageFactory.create(image_credit='Credit B')
        results = ImageEmbedHandler.expand_db_attributes_many([
            {'id': str(img1.pk), 'format': 'left', 'alt': 'img1'},
            {'id': str(img2.pk), 'format': 'right', 'alt': 'img2'},
        ])
        assert len(results) == 2
        assert 'data-image-credit="Credit A"' in results[0]
        assert 'data-image-credit="Credit B"' in results[1]

    def test_mixed_credited_and_uncredited(self):
        img_with = AplansImageFactory.create(image_credit='Reuters')
        img_without = AplansImageFactory.create(image_credit='')
        results = ImageEmbedHandler.expand_db_attributes_many([
            {'id': str(img_with.pk), 'format': 'fullwidth', 'alt': 'a'},
            {'id': str(img_without.pk), 'format': 'fullwidth', 'alt': 'b'},
        ])
        assert 'data-image-credit="Reuters"' in results[0]
        assert 'data-image-credit' not in results[1]


class TestImageEmbedHandlerBaseBehavior:
    """Tests that base Wagtail behavior is preserved."""

    def test_nonexistent_image_returns_empty_img(self):
        result = ImageEmbedHandler.expand_db_attributes({
            'id': '999999',
            'format': 'left',
            'alt': '',
        })
        assert result == '<img alt="">'

    def test_alt_text_preserved(self):
        image = AplansImageFactory.create()
        result = ImageEmbedHandler.expand_db_attributes({
            'id': str(image.pk),
            'format': 'left',
            'alt': 'A beautiful sunset',
        })
        assert 'alt="A beautiful sunset"' in result

    def test_css_class_preserved(self):
        image = AplansImageFactory.create()
        result = ImageEmbedHandler.expand_db_attributes({
            'id': str(image.pk),
            'format': 'left',
            'alt': 'test',
        })
        assert 'class="richtext-image left"' in result

    def test_identifier_is_image(self):
        assert ImageEmbedHandler.identifier == 'image'


class TestImageEmbedHandlerRegistration:
    """Tests that the custom handler is registered in Wagtail's feature registry."""

    def test_custom_handler_registered_in_feature_registry(self):
        from wagtail.rich_text import features

        embed_types = features.get_embed_types()
        assert embed_types['image'] is ImageEmbedHandler

    def test_expand_db_html_uses_custom_handler(self):
        """End-to-end: expand_db_html should produce data-image-credit."""
        from wagtail.rich_text import expand_db_html

        image = AplansImageFactory.create(image_credit='AP Photo')
        html = f'<embed embedtype="image" id="{image.pk}" format="fullwidth" alt="test"/>'
        result = expand_db_html(html)
        assert 'data-image-credit="AP Photo"' in result
