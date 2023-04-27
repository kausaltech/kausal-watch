from admin_site.apps import _get_language_choices


def test_language_choices():
    # _get_language_choices breaks if a language unknown to Django is in settings.LANGUAGES but not in
    # settings.LOCAL_LANGUAGE_NAMES
    assert _get_language_choices()  # should not raise an exception, and at least shouldn't be empty either
