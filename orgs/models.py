from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from treebeard.mp_tree import MP_Node
from wagtail.admin.edit_handlers import FieldPanel

from admin_site.wagtail import CondensedInlinePanel


# TODO: Generalize and put in some other app's models.py
class Node(MP_Node, ClusterableModel):
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


class OrganizationClass(models.Model):
    identifier = models.CharField(max_length=255, unique=True, editable=False)
    name = models.CharField(max_length=255)

    created_time = models.DateTimeField(auto_now_add=True,
                                        help_text=_('The time at which the resource was created'))
    last_modified_time = models.DateTimeField(auto_now=True,
                                              help_text=_('The time at which the resource was updated'))

    def __str__(self):
        return f'{self.name} ({self.identifier})'


class Organization(Node):
    # base_form_class = OrganizationForm
    # This doesn't work because OrganizationForm depends on this class. We set base_form_class after defining
    # OrganizationForm.

    panels = Node.panels + [
        FieldPanel('classification'),
        FieldPanel('abbreviation'),
        FieldPanel('founding_date'),
        FieldPanel('dissolution_date'),
        CondensedInlinePanel('identifiers', panels=[
            FieldPanel('namespace'),
            FieldPanel('identifier'),
        ])
    ]

    # Different identifiers, depending on origin (namespace), are stored in OrganizationIdentifier

    classification = models.ForeignKey(OrganizationClass,
                                       on_delete=models.PROTECT,
                                       blank=True,
                                       null=True,
                                       help_text=_('An organization category, e.g. committee'))

    name = models.CharField(max_length=255,
                            help_text=_('A primary name, e.g. a legally recognized name'))
    abbreviation = models.CharField(max_length=50,
                                    blank=True,
                                    help_text=_('A commonly used abbreviation'))
    # TODO: Write / copy management command for generating the following
    distinct_name = models.CharField(max_length=400,
                                     editable=False,
                                     null=True,
                                     help_text=_('A distinct name for this organization (generated automatically)'))
    founding_date = models.DateField(blank=True,
                                     null=True,
                                     help_text=_('A date of founding'))
    dissolution_date = models.DateField(blank=True,
                                        null=True,
                                        help_text=_('A date of dissolution'))
    # TODO
    # admin_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='admin_organizations')
    # regular_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True,
    #                                        related_name='organization_memberships')
    created_time = models.DateTimeField(auto_now_add=True,
                                        help_text=_('The time at which the resource was created'))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   # related_name='created_organizations',
                                   related_name='created_organizations',
                                   null=True,
                                   blank=True,
                                   editable=False,
                                   on_delete=models.SET_NULL)
    last_modified_time = models.DateTimeField(auto_now=True,
                                              help_text=_('The time at which the resource was updated'))
    last_modified_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                         # related_name='modified_organizations',
                                         related_name='modified_organizations',
                                         null=True,
                                         blank=True,
                                         editable=False,
                                         on_delete=models.SET_NULL)

    def __str__(self):
        if self.distinct_name:
            name = self.distinct_name
        else:
            name = self.name
        if self.dissolution_date:
            return self.name + ' (dissolved)'
        return name


class Namespace(models.Model):
    identifier = models.CharField(max_length=255, unique=True, editable=False)
    name = models.CharField(max_length=255)
    user_editable = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.name} ({self.identifier})'


class OrganizationIdentifier(models.Model):
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['namespace', 'identifier'], name='unique_identifier_in_namespace')
        ]

    organization = ParentalKey(Organization, on_delete=models.CASCADE, related_name='identifiers')
    identifier = models.CharField(max_length=255)
    namespace = models.ForeignKey(Namespace, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.identifier} @ {self.namespace.name}'
