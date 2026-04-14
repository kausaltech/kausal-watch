from admin_site.apps import _get_language_choices


def test_language_choices():
    # _get_language_choices breaks if a language unknown to Django is in settings.LANGUAGES but not in
    # settings.LOCAL_LANGUAGE_NAMES
    assert _get_language_choices()  # should not raise an exception, and at least shouldn't be empty either


def test_rich_text_default_features_include_superscript():
    from wagtail.rich_text import features

    default = features.get_default_features()  # type: ignore[attr-defined]
    assert 'superscript' in default
    assert 'subscript' in default


def test_rich_text_default_features_not_duplicated():
    """
    Ensure no feature is registered more than once.

    Module-level ModelForm classes whose model has RichTextFields can trigger
    re-entrant feature scanning during Wagtail hook discovery, doubling every
    default feature.  This test catches that regression.
    """
    from collections import Counter

    from wagtail.rich_text import features

    default = features.get_default_features()  # type: ignore[attr-defined]
    duplicates = {f: n for f, n in Counter(default).items() if n > 1}
    assert not duplicates, f'Duplicate default rich-text features: {duplicates}'
