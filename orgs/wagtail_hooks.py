from django.utils.translation import gettext_lazy as _
from wagtail.contrib.modeladmin.options import modeladmin_register

from .models import Organization

# Only define and register model admin for Organization if tree_editor module exists
# TODO: Instead of conditional imports, monkey-patch things in the proprietary extensions
try:
    from tree_editor.wagtail_admin import NodeAdmin
except ImportError:
    pass
else:
    class OrganizationAdmin(NodeAdmin):
        model = Organization
        menu_label = _("Organizations")
        menu_icon = 'fa-sitemap'
        menu_order = 9000

    modeladmin_register(OrganizationAdmin)
