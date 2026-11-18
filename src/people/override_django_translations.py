def _(s: str) -> str:
    return s


django_standard_messages_to_override = [
    # Wagtail has no Danish or Latvian translation of the snippet delete message
    _("%(model_name)s '%(object)s' deleted."),
]
