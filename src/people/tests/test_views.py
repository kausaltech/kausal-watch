from __future__ import annotations

import pytest


def test_reset_password_view_accepts_as_view_kwargs():
    """
    as_view() must accept all kwargs that are passed when the view is used.

    Django's View.as_view() checks hasattr(cls, key) for each kwarg.
    Type annotations without default values do NOT create class attributes,
    so they will cause TypeError if passed as kwargs to as_view().

    This test ensures that ResetPasswordView.target_person_pk has a default value
    (or is otherwise a class attribute) so it can be passed to as_view().
    """
    from people.views import ResetPasswordView

    # Verify the class attribute exists
    assert hasattr(ResetPasswordView, 'target_person_pk'), 'ResetPasswordView must have target_person_pk as a class attribute'

    # Verify as_view() accepts the kwarg
    try:
        ResetPasswordView.as_view(
            model_admin=None,
            target_person_pk='1',
        )
    except TypeError as e:
        if 'invalid keyword' in str(e):
            pytest.fail(f'as_view() rejected a keyword argument: {e}')
        raise


def test_impersonate_user_view_accepts_as_view_kwargs():
    """
    as_view() must accept all kwargs that are passed when the view is used.

    This test ensures that ImpersonateUserView.target_person_pk has a default value
    (or is otherwise a class attribute) so it can be passed to as_view().
    """
    from people.views import ImpersonateUserView

    # Verify the class attribute exists
    assert hasattr(ImpersonateUserView, 'target_person_pk'), 'ImpersonateUserView must have target_person_pk as a class attribute'

    # Verify as_view() accepts the kwarg
    try:
        ImpersonateUserView.as_view(
            model_admin=None,
            target_person_pk='1',
        )
    except TypeError as e:
        if 'invalid keyword' in str(e):
            pytest.fail(f'as_view() rejected a keyword argument: {e}')
        raise
