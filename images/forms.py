from __future__ import annotations

from typing import TYPE_CHECKING

from wagtail.images.forms import BaseImageForm
from wagtail.log_actions import log

if TYPE_CHECKING:
    from images.models import AplansImage


class AplansImageForm(BaseImageForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.get('user')
        self.user = user
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance: AplansImage = super().save(commit=commit)
        if commit is False:
            return instance

        log(
            instance=instance,
            action='file.created_or_updated',
            user=self.user,
        )
        return instance
