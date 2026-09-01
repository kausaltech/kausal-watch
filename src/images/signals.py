from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver
from wagtail.log_actions import log

from images.forms import _FORM_USER_ATTR
from images.models import AplansImage

_UNSET = object()


@receiver(post_save, sender=AplansImage)
def log_form_save(sender, instance, **kwargs):
    """
    Log a file.created_or_updated audit entry whenever an AplansImage is saved through AplansImageForm.

    AplansImageForm tags the instance with the form's user before delegating to
    super().save(); when the model is then saved (either by the form itself or
    by Wagtail's multi-upload AddView via instance.save() after form.save(commit=False)),
    this handler picks up the tag and writes the log entry exactly once.
    """
    user = getattr(instance, _FORM_USER_ATTR, _UNSET)
    if user is _UNSET:
        return
    delattr(instance, _FORM_USER_ATTR)
    log(instance=instance, action='file.created_or_updated', user=user)
