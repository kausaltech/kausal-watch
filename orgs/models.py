from django.core.exceptions import PermissionDenied
from django.db import models
from django.template.loader import render_to_string
from treebeard.mp_tree import MP_Node
from wagtail.admin.edit_handlers import FieldPanel


# TODO: Generalize and put in some other app's models.py
class Node(MP_Node):
    class Meta:
        abstract = True

    name = models.CharField(max_length=255)

    node_order_by = ['name']

    # We could also define panels in the ModelAdmin class.
    panels = [
        FieldPanel('parent'),  # virtual field, needs to be specified in the form
        FieldPanel('name'),
    ]

    public_fields = ['id', 'name']

    def delete(self):
        if self.is_root():
            raise PermissionDenied("Cannot delete root")
        super().delete()

    def get_as_listing_header(self):
        """Build HTML representation of node with title & depth indication."""
        depth = self.get_depth()
        rendered = render_to_string(
            'orgs/node_list_header.html',
            {
                'depth': depth,
                'depth_minus_1': depth - 1,
                'is_root': self.is_root(),
                'name': self.name,
            }
        )
        return rendered
    get_as_listing_header.short_description = 'Name'
    get_as_listing_header.admin_order_field = 'name'

    # Duplicate get_parent from super class just to set short_description below
    def get_parent(self, *args, **kwargs):
        return super().get_parent(*args, **kwargs)
    get_parent.short_description = 'Parent'

    def __str__(self):
        return self.name


class Organization(Node):
    # base_form_class = OrganizationForm
    # This doesn't work because OrganizationForm depends on this class. We set base_form_class after defining
    # OrganizationForm.

    # TODO: Add fields
    pass
