from __future__ import annotations

import functools
import typing
from typing import Optional
from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.db.models import Q, Count
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from treebeard.mp_tree import MP_Node, MP_NodeQuerySet
from wagtail.core.fields import RichTextField
from wagtail.search import index

from aplans.utils import PlanRelatedModel, get_default_language, get_supported_languages

if typing.TYPE_CHECKING:
    from actions.models import Plan
    from users.models import User


# TODO: Generalize and put in some other app's models.py
class Node(MP_Node, ClusterableModel):
    class Meta:
        abstract = True

    name = models.CharField(max_length=255, verbose_name=_("name"))

    # Disabled `node_order_by` for now. If we used this, then we wouldn't be able to use "left sibling" to specify a
    # position of a node, e.g., when calling the REST API from the grid editor. Since it would be significant work to
    # change it (e.g., disable move handles in grid editor, distinguish cases in the backend whether model has
    # node_order_by, etc.) and some customers might want to order their organizations in some way, I decided to disable
    # `node_order_by`.
    # node_order_by = ['name']

    public_fields = ['id', 'name']

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
    get_as_listing_header.short_description = _('Name')
    get_as_listing_header.admin_order_field = 'name'

    # Duplicate get_parent from super class just to set short_description below
    def get_parent(self, *args, **kwargs):
        return super().get_parent(*args, **kwargs)
    get_parent.short_description = _('Parent')

    def __str__(self):
        return self.name


class OrganizationClass(models.Model):
    class Meta:
        # FIXME: Probably we can't rely on this with i18n
        ordering = ['name']

    identifier = models.CharField(max_length=255, unique=True, editable=False)
    name = models.CharField(max_length=255)

    created_time = models.DateTimeField(auto_now_add=True,
                                        help_text=_('The time at which the resource was created'))
    last_modified_time = models.DateTimeField(auto_now=True,
                                              help_text=_('The time at which the resource was updated'))

    i18n = TranslationField(fields=('name',))

    def __str__(self):
        return self.name


class OrganizationQuerySet(MP_NodeQuerySet):
    def editable_by_user(self, user: User):
        if user.is_superuser:
            return self
        # person = user.get_corresponding_person()
        # if not person:
        #     return self.none()
        #
        # metadata_admin_orgs = person.metadata_adminable_organizations.only('path')
        # filters = [Q(path__startswith=org.path) for org in metadata_admin_orgs]
        # if not filters:
        #     return self.none()
        # qs = functools.reduce(lambda x, y: x | y, filters)
        # return self.filter(qs)

        # For now, for general plan admins, we allow editing all organizations related to the plan
        # FIXME: We may want to remove this again and rely on OrganizationMetadataAdmin using the commented-out code
        # above
        adminable_plans = user.get_adminable_plans()
        if not adminable_plans:
            return self.none()
        q = Q()
        for plan in adminable_plans:
            available_orgs = Organization.objects.available_for_plan(plan)
            q |= Q(pk__in=available_orgs)
        return self.filter(q)

    def available_for_plan(self, plan):
        all_related = plan.related_organizations.all()
        for org in plan.related_organizations.all():
            all_related |= org.get_descendants()
        if plan.organization:
            all_related |= Organization.objects.filter(id=plan.organization.id)
            all_related |= plan.organization.get_descendants()
        return self.filter(id__in=all_related)

    def user_is_plan_admin_for(self, user: User, plan: Optional[Plan] = None):
        person = user.get_corresponding_person()
        adm_objs = OrganizationPlanAdmin.objects.filter(person=person)
        if plan is not None:
            adm_objs = adm_objs.filter(plan=plan)
        admin_orgs = self.model.objects.filter(organization_plan_admins__in=adm_objs).only('path').distinct()
        if not admin_orgs:
            return self.none()
        filters = [Q(path__startswith=org.path) for org in admin_orgs]
        qs = functools.reduce(lambda x, y: x | y, filters)
        return self.filter(qs)

    def annotate_action_count(self, plan: Plan | None = None):
        if plan is not None:
            annotate_filter = Q(responsible_actions__action__plan=plan)
        else:
            annotate_filter = None
        qs = self.annotate(action_count=Count(
            'responsible_actions__action', distinct=True, filter=annotate_filter
        ))
        return qs

    def annotate_contact_person_count(self, plan: Plan | None = None):
        if plan is not None:
            annotate_filter = Q(people__contact_for_actions__plan=plan)
        else:
            annotate_filter = None
        qs = self.annotate(contact_person_count=Count(
            'people', distinct=True, filter=annotate_filter
        ))
        return qs


class OrganizationManager(gis_models.Manager):
    """Duplicate MP_NodeManager but use OrganizationQuerySet instead of MP_NodeQuerySet."""
    def get_queryset(self):
        return OrganizationQuerySet(self.model).order_by('path')

    def editable_by_user(self, user):
        return self.get_queryset().editable_by_user(user)

    def user_is_plan_admin_for(self, user: User, plan: Optional[Plan] = None):
        return self.get_queryset().user_is_plan_admin_for(user, plan)

    def available_for_plan(self, plan):
        return self.get_queryset().available_for_plan(plan)


class Organization(index.Indexed, Node, gis_models.Model):
    # Different identifiers, depending on origin (namespace), are stored in OrganizationIdentifier
    class Meta:
        verbose_name = _("organization")
        verbose_name_plural = _("organizations")

    classification = models.ForeignKey(OrganizationClass,
                                       on_delete=models.PROTECT,
                                       blank=True,
                                       null=True,
                                       verbose_name=_("Classification"),
                                       help_text=_('An organization category, e.g. committee'))
    # TODO: Check if we can / should remove this since already `Node` specifies `name`
    name = models.CharField(max_length=255,
                            help_text=_('A primary name, e.g. a legally recognized name'))
    abbreviation = models.CharField(max_length=50,
                                    blank=True,
                                    verbose_name=_("Short name"),
                                    help_text=_('A simplified short version of name for the general public'))
    internal_abbreviation = models.CharField(max_length=50,
                                             blank=True,
                                             verbose_name=_("Internal abbreviation"),
                                             help_text=_('An internally used abbreviation'))
    distinct_name = models.CharField(max_length=400,
                                     editable=False,
                                     null=True,
                                     help_text=_('A distinct name for this organization (generated automatically)'))
    logo = models.ForeignKey(
        'images.AplansImage',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        help_text=_('An optional logo for this organization'),
    )
    description = RichTextField(blank=True, verbose_name=_('description'))
    url = models.URLField(blank=True, verbose_name=_('URL'))
    founding_date = models.DateField(blank=True,
                                     null=True,
                                     help_text=_('A date of founding'))
    dissolution_date = models.DateField(blank=True,
                                        null=True,
                                        help_text=_('A date of dissolution'))
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
    metadata_admins = models.ManyToManyField('people.Person',
                                             through='orgs.OrganizationMetadataAdmin',
                                             related_name='metadata_adminable_organizations',
                                             blank=True)
    primary_language = models.CharField(max_length=8, choices=get_supported_languages(), default=get_default_language)
    location = gis_models.PointField(verbose_name=_('Location'), srid=4326, null=True, blank=True)

    i18n = TranslationField(fields=('name', 'abbreviation'), default_language_field='primary_language')

    objects = OrganizationManager()

    public_fields = ['id', 'name', 'abbreviation', 'internal_abbreviation', 'parent']

    search_fields = [
        index.AutocompleteField('name', partial_match=True),
        index.AutocompleteField('abbreviation', partial_match=True),
    ]

    @property
    def parent(self):
        return self.get_parent()

    def generate_distinct_name(self, levels=1):
        # FIXME: This relies on legacy identifiers
        if self.classification is not None and self.classification.identifier.startswith('helsinki:'):
            ROOTS = ['Kaupunki', 'Valtuusto', 'Hallitus', 'Toimiala', 'Lautakunta', 'Toimikunta', 'Jaosto']
            stopper_classes = OrganizationClass.objects\
                .filter(identifier__startswith='helsinki:', name__in=ROOTS).values_list('id', flat=True)
            stopper_parents = Organization.objects\
                .filter(classification__identifier__startswith='helsinki:', name='Kaupunginkanslia',
                        dissolution_date=None)\
                .values_list('id', flat=True)
        else:
            stopper_classes = []
            stopper_parents = []

        if (stopper_classes and self.classification_id in stopper_classes) or \
                (stopper_parents and self.id in stopper_parents):
            return self.name

        name = self.name
        parent = self.get_parent()
        for level in range(levels):
            if parent is None:
                break
            if parent.abbreviation:
                parent_name = parent.abbreviation
            else:
                parent_name = parent.name
            name = "%s / %s" % (parent_name, name)
            if stopper_classes and parent.classification_id in stopper_classes:
                break
            if stopper_parents and parent.id in stopper_parents:
                break
            parent = parent.get_parent()

        return name

    def user_can_edit(self, user):
        if user.is_superuser:
            return True
        person = user.get_corresponding_person()
        if person:
            ancestors = self.get_ancestors() | Organization.objects.filter(pk=self.pk)
            intersection = ancestors & person.metadata_adminable_organizations.all()
            if intersection.exists():
                return True

        # For now, for general plan admins, we allow editing all organizations related to the plan
        # FIXME: We may want to remove this again and rely on OrganizationMetadataAdmin using the code above
        for plan in user.get_adminable_plans():
            available_orgs = Organization.objects.available_for_plan(plan)
            if available_orgs.filter(pk=self.pk).exists():
                return True

        return False

    def user_can_change_related_to_plan(self, user, plan):
        return user.is_general_admin_for_plan(plan)

    def get_fully_qualified_name(self):
        parents = []
        org = self.get_parent()
        while org is not None:
            parents.append(org)
            org = org.get_parent()
        name = self.name
        if self.internal_abbreviation:
            name = f'{self.internal_abbreviation} - {name}'
        if parents:
            def get_org_path_str(org: Organization):
                # if org.abbreviation:
                #     return org.abbreviation
                return org.name

            parent_path = ' | '.join([get_org_path_str(org) for org in parents])
            name += ' (%s)' % parent_path
        return name

    def print_tree(self):
        from rich.tree import Tree
        from rich import print

        def get_label(org: Organization):
            return '%s ([green]%d actions; [blue]%d persons)' % (
                org.name, org.action_count, org.contact_person_count
            )

        def add_children(org: Organization, tree: Tree):
            children: list[Organization] = list(
                org.get_children().annotate_action_count()  # type: ignore
                .annotate_contact_person_count().order_by('name')
            )
            if not children:
                return
            for child in children:
                child_tree = tree.add(get_label(child))
                add_children(child, child_tree)

        root_org = Organization.objects.filter(id=self.id)\
            .annotate_action_count().annotate_contact_person_count().first()
        root_tree = Tree(get_label(root_org))
        add_children(root_org, root_tree)
        print(root_tree)

    def __str__(self):
        if self.name is None:
            return '[None]'
        fq_name = self.get_fully_qualified_name()
        if self.dissolution_date:
            fq_name += ' [dissolved]'
        return fq_name


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


class OrganizationPlanAdmin(models.Model, PlanRelatedModel):
    """Person who can administer plan-specific content that is related to the organization."""
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['organization', 'plan', 'person'], name='unique_organization_plan_admin')
        ]
        verbose_name = _("plan admin")
        verbose_name_plural = _("plan admins")

    organization = ParentalKey(
        Organization, on_delete=models.CASCADE, related_name='organization_plan_admins', verbose_name=_('organization'),
    )
    plan = models.ForeignKey(
        'actions.Plan', on_delete=models.CASCADE, related_name='organization_plan_admins', verbose_name=_('plan')
    )
    person = models.ForeignKey(
        'people.Person', on_delete=models.CASCADE, related_name='organization_plan_admins', verbose_name=_('person')
    )

    def __str__(self):
        return f'{self.person} ({self.plan})'


class OrganizationMetadataAdmin(models.Model):
    """Person who can administer data of (descendants of) an organization but, in general, no plan-specific content."""
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['organization', 'person'], name='unique_organization_metadata_admin')
        ]
        verbose_name = _("metadata admin")
        verbose_name_plural = _("metadata admins")

    organization = ParentalKey(
        Organization,
        on_delete=models.CASCADE,
        verbose_name=_('organization'),
        related_name='organization_metadata_admins',
    )
    person = models.ForeignKey(
        'people.Person',
        on_delete=models.CASCADE,
        verbose_name=_('person'),
    )

    def __str__(self):
        return str(self.person)
