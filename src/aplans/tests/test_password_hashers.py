from __future__ import annotations

from django.contrib.auth.hashers import check_password, make_password


def test_new_passwords_use_a_cheap_hasher() -> None:
    """
    Tests create hundreds of users, so they must not pay for a production-strength KDF.

    See the comment next to PASSWORD_HASHERS in the settings module for the measured cost.
    """
    assert make_password('correct horse battery staple').startswith('md5$')


def test_passwords_hashed_by_the_production_hasher_still_verify() -> None:
    """The production hashers stay configured so existing encoded passwords keep validating."""
    encoded = make_password('correct horse battery staple', hasher='pbkdf2_sha256')
    assert check_password('correct horse battery staple', encoded)
    assert not check_password('hunter2', encoded)
