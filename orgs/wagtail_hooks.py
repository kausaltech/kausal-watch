from django.utils.translation import gettext_lazy as _
from wagtail.contrib.modeladmin.options import modeladmin_register

from .models import Organization

# Only define and register model admin for Organization if tree_editor module exists
try:
    from tree_editor.forms import NodeForm
    from tree_editor.wagtail_admin import NodeAdmin
except ImportError:
    pass
else:
    class OrganizationForm(NodeForm):
        class Meta:
            model = Organization
            fields = ['name']

    # FIXME: This should be done in the model definition, but we have a circular
    # dependency.
    Organization.base_form_class = OrganizationForm

    class OrganizationAdmin(NodeAdmin):
        model = Organization
        menu_label = _("Organizations")
        menu_icon = 'fa-sitemap'
        menu_order = 9000

    modeladmin_register(OrganizationAdmin)
