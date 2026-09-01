from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from grapple.helpers import register_streamfield_block

from kausal_common.blocks.base import ContentBlockBase


@register_streamfield_block
class ChangeLogMessageBlock(ContentBlockBase):
    """Show the latest change history message in the details page of an action, category, and later also an indicator."""

    class Meta:
        label = _('Latest change history message')
