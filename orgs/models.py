from __future__ import annotations

import functools
import typing
import uuid
from typing import ClassVar, Iterable, Self, Sequence

import reversion
from django.conf import settings
from django.contrib import admin
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from modeltrans.manager import MultilingualQuerySet
from wagtail.fields import RichTextField
from wagtail.search import index

from treebeard.mp_tree import MP_Node, MP_NodeQuerySet

from kausal_common.models.types import MLModelManager, RevManyToMany
from kausal_common.organizations.models import (
    BaseOrganization,
    BaseOrganizationClass,
    BaseOrganizationIdentifier,
    BaseOrganizationMetadataAdmin,
    BaseNamespace,
    BaseOrganizationQuerySet,
    Node,
)

from aplans.utils import ModelWithPrimaryLanguage, PlanDefaultsModel, PlanRelatedModel, get_supported_languages

if typing.TYPE_CHECKING:
    from django.db.models import QuerySet
    from modelcluster.fields import PK

    from kausal_common.models.types import FK, M2M, RevManyQS

    from actions.models import Action, Plan
    from actions.models.action import ActionResponsibleParty
    from actions.models.plan import PlanQuerySet
    from images.models import AplansImage
    from people.models import Person
    from users.models import User


class OrganizationClass(BaseOrganizationClass):
    pass

class OrganizationQuerySet(BaseOrganizationQuerySet):
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
        q = Q(pk__in=[])  # always false; Q() doesn't cut it; https://stackoverflow.com/a/39001190/14595546
        for plan in adminable_plans:
            available_orgs = Organization.objects.get_queryset().available_for_plan(plan)
            q |= Q(pk__in=available_orgs)
        return self.filter(q)

    @classmethod
    def _available_for_plan(cls, plan: Plan) -> QuerySet[Organization]:
        all_related = plan.related_organizations.all()
        for org in plan.related_organizations.all():
            all_related |= org.get_descendants()
        if plan.organization:
            all_related |= Organization.objects.filter(id=plan.organization.pk)
            all_related |= plan.organization.get_descendants()
        return all_related

    def available_for_plan(self, plan: Plan):
        return self.filter(id__in=self._available_for_plan(plan))

    def available_for_plans(self, plans: Sequence[Plan] | PlanQuerySet):
        query = Q(pk__in=[])  # always false; Q() doesn't cut it; https://stackoverflow.com/a/39001190/14595546
        for pl in plans:
            query |= Q(id__in=self._available_for_plan(pl))
        return self.filter(query)

    def user_is_plan_admin_for(self, user: User, plan: Plan | None = None):
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
        qs = self.annotate(
            action_count=Count(
                'responsible_actions__action',
                distinct=True,
                filter=annotate_filter,
            )
        )
        return qs

    def annotate_contact_person_count(self, plan: Plan | None = None):
        if plan is not None:
            annotate_filter = Q(people__contact_for_actions__plan=plan)
        else:
            annotate_filter = None
        qs = self.annotate(
            contact_person_count=Count(
                'people',
                distinct=True,
                filter=annotate_filter,
            )
        )
        return qs


_OrganizationManager = models.Manager.from_queryset(OrganizationQuerySet)


class OrganizationManager(MLModelManager['Organization', OrganizationQuerySet], _OrganizationManager): ...


del _OrganizationManager


@reversion.register()
class Organization(BaseOrganization, PlanDefaultsModel, Node[OrganizationQuerySet]):
    VIEWSET_CLASS = 'orgs.wagtail_admin.OrganizationViewSet'  # for AdminButtonsMixin

    logo: FK[AplansImage | None] = models.ForeignKey(
        'images.AplansImage',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        help_text=_(
            'Organization logo. Please provide a square image (min. 250x250px). '
            "The logo used for the organization's social media often works best."
        ),
    )

    objects: ClassVar[OrganizationManager] = OrganizationManager()  # type: ignore[assignment]


    def initialize_plan_defaults(self, plan):
        assert not self.primary_language
        self.primary_language = plan.primary_language

    def generate_distinct_name(self, levels=1):
        # FIXME: This relies on legacy identifiers
        stopper_classes: list[int]
        stopper_parents: list[int]

        if self.classification is not None and self.classification.identifier.startswith('helsinki:'):
            ROOTS = ['Kaupunki', 'Valtuusto', 'Hallitus', 'Toimiala', 'Lautakunta', 'Toimikunta', 'Jaosto']  # noqa: N806
            stopper_classes = list(
                OrganizationClass.objects.filter(identifier__startswith='helsinki:', name__in=ROOTS).values_list('id', flat=True)
            )
            stopper_parents = list(
                Organization.objects.filter(
                    classification__identifier__startswith='helsinki:', name='Kaupunginkanslia', dissolution_date=None
                ).values_list('id', flat=True)
            )
        else:
            stopper_classes = []
            stopper_parents = []

        if (stopper_classes and self.classification_id in stopper_classes) or (stopper_parents and self.id in stopper_parents):
            return self.name

        name = self.name
        parent = self.get_parent()
        for _level in range(levels):
            if parent is None:
                break
            if parent.abbreviation:
                parent_name = parent.abbreviation
            else:
                parent_name = parent.name
            name = '%s / %s' % (parent_name, name)
            if stopper_classes and parent.classification_id in stopper_classes:
                break
            if stopper_parents and parent.id in stopper_parents:
                break
            parent = parent.get_parent()

        return name

    def user_can_edit(self, user: User):
        if user.is_superuser:
            return True
        person = user.get_corresponding_person()
        if person:
            ancestors = self.get_ancestors() | Organization.objects.get_queryset().filter(pk=self.pk)  # pyright: ignore
            intersection = ancestors & person.metadata_adminable_organizations.all()
            if intersection.exists():
                return True

        # For now, for general plan admins, we allow editing all organizations related to the plan
        # FIXME: We may want to remove this again and rely on OrganizationMetadataAdmin using the code above
        if not user.is_general_admin_for_plan():
            return False
        for plan in user.get_adminable_plans():
            available_orgs = Organization.objects.get_queryset().available_for_plan(plan)
            if available_orgs.filter(pk=self.pk).exists():
                return True

        return False

    def user_can_change_related_to_plan(self, user, plan):
        return user.is_general_admin_for_plan(plan)

    @classmethod
    def make_orgs_by_path(cls, orgs: Iterable[Organization]) -> dict[str, Organization]:
        return {org.path: org for org in orgs}

    def get_fully_qualified_name(self, orgs_by_path: dict[str, Organization] | None = None):
        parents = []
        org_map = orgs_by_path
        if org_map is None:
            if self.depth > 1:
                org_map = {org.path: org for org in self.get_ancestors()}
            else:
                org_map = {}
        org = self
        while org.depth > 1:
            parent_path = self._get_basepath(org.path, org.depth - 1)
            org = org_map[parent_path]
            parents.append(org)

        name = self.name
        if self.internal_abbreviation:
            name = f'{self.internal_abbreviation} - {name}'
        if parents:

            def get_org_path_str(org: Organization) -> str:
                # if org.abbreviation:
                #     return org.abbreviation
                return org.name

            parent_path = ' | '.join([get_org_path_str(org) for org in parents])
            name += ' (%s)' % parent_path
        return name

    def print_tree(self):
        from rich import print
        from rich.tree import Tree

        def get_label(org: Organization) -> str:
            return '%s ([green]%d actions; [blue]%d persons)' % (
                org.name,
                org.action_count,
                org.contact_person_count,  # pyright: ignore
            )

        def add_children(org: Organization, tree: Tree) -> None:
            children: list[Organization] = list(
                org.get_children()
                .annotate_action_count()  # type: ignore
                .annotate_contact_person_count()
                .order_by('name'),
            )
            if not children:
                return
            for child in children:
                child_tree = tree.add(get_label(child))
                add_children(child, child_tree)

        root_org = (
            Organization.objects.get_queryset().filter(id=self.pk).annotate_action_count().annotate_contact_person_count().first()
        )
        assert root_org is not None
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


class Namespace(BaseNamespace):
    pass


class OrganizationIdentifier(BaseOrganizationIdentifier):
    pass



class OrganizationPlanAdmin(PlanRelatedModel):
    """Person who can administer plan-specific content that is related to the organization."""

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['organization', 'plan', 'person'], name='unique_organization_plan_admin'),
        ]
        verbose_name = _('plan admin')
        verbose_name_plural = _('plan admins')

    organization: PK = ParentalKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='organization_plan_admins',
        verbose_name=_('organization'),
    )
    plan: FK[Plan] = models.ForeignKey(
        'actions.Plan',
        on_delete=models.CASCADE,
        related_name='organization_plan_admins',
        verbose_name=_('plan'),
    )
    person: FK[Person] = models.ForeignKey(
        'people.Person',
        on_delete=models.CASCADE,
        related_name='organization_plan_admins',
        verbose_name=_('person'),
    )

    def __str__(self):
        return f'{self.person} ({self.plan})'


class OrganizationMetadataAdmin(BaseOrganizationMetadataAdmin):
    pass
