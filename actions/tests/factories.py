import datetime
from factory import RelatedFactory, Sequence, SubFactory, post_generation
from factory.django import DjangoModelFactory

from actions.models import CategoryTypeMetadata
from people.tests.factories import PersonFactory
from content.tests.factories import SiteGeneralContentFactory


class OrganizationFactory(DjangoModelFactory):
    class Meta:
        model = 'django_orghierarchy.Organization'

    id = Sequence(lambda i: f'organization{i}')
    name = Sequence(lambda i: f'Organization {i}')
    abbreviation = Sequence(lambda i: f'org{i}')


# https://factoryboy.readthedocs.io/en/stable/recipes.html#example-django-s-profile
# @factory.django.mute_signals(post_save)
class PlanFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.Plan'

    organization = SubFactory(OrganizationFactory)
    name = Sequence(lambda i: f'Plan {i}')
    identifier = Sequence(lambda i: f'plan{i}')
    site_url = Sequence(lambda i: f'https://plan{i}.example.com')
    general_content = RelatedFactory(SiteGeneralContentFactory, factory_related_name='plan')


class ActionStatusFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionStatus'

    plan = SubFactory(PlanFactory)
    name = "Test action status"
    identifier = 'test-action-status'


class ActionImplementationPhaseFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionImplementationPhase'

    plan = SubFactory(PlanFactory)
    name = "Test action implementation phase"
    identifier = 'test-aip'


class ActionScheduleFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionSchedule'

    plan = SubFactory(PlanFactory)
    name = "Test action schedule"
    begins_at = datetime.date(2020, 1, 1)


class ActionImpactFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionImpact'

    plan = SubFactory(PlanFactory)
    name = "Test action impact"
    identifier = 'test-action-impact'


class CategoryTypeFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryType'

    plan = SubFactory(PlanFactory)
    identifier = Sequence(lambda i: f'ct{i}')
    name = Sequence(lambda i: f'CategoryType {i}')


class CategoryTypeMetadataFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryTypeMetadata'

    type = SubFactory(CategoryTypeFactory)
    identifier = Sequence(lambda i: f'ctm{i}')
    name = Sequence(lambda i: f'CategoryTypeMetadata {i}')
    format = CategoryTypeMetadata.MetadataFormat.RICH_TEXT


class CategoryTypeMetadataChoiceFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryTypeMetadataChoice'

    metadata = SubFactory(CategoryTypeMetadataFactory)
    identifier = Sequence(lambda i: f'ctmc{i}')
    name = Sequence(lambda i: f'CategoryTypeMetadataChoice {i}')


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.Category'

    type = SubFactory(CategoryTypeFactory)
    identifier = Sequence(lambda i: f'category{i}')
    name = Sequence(lambda i: f'Category {i}')


class CategoryTypeMetadataFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryTypeMetadata'

    type = SubFactory(CategoryTypeFactory)
    identifier = Sequence(lambda i: f'category-type-metadata-{i}')
    name = Sequence(lambda i: f'Category type metadata {i}')
    format = CategoryTypeMetadata.MetadataFormat.RICH_TEXT


class CategoryMetadataRichTextFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryMetadataRichText'

    metadata = SubFactory(CategoryTypeMetadataFactory)
    category = SubFactory(CategoryFactory)
    text = Sequence(lambda i: f'CategoryMetadataRichText {i}')


class ActionFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.Action'

    plan = SubFactory(PlanFactory)
    name = "Test action"
    identifier = 'test-action'
    official_name = name
    description = "Action description"
    impact = SubFactory(ActionImpactFactory)
    status = SubFactory(ActionStatusFactory)
    implementation_phase = SubFactory(ActionImplementationPhaseFactory)
    completion = 99

    @post_generation
    def schedule(self, create, extracted, **kwargs):
        if create:
            if extracted is None:
                extracted = [ActionScheduleFactory(plan=self.plan)]
            for schedule in extracted:
                self.schedule.add(schedule)

    @post_generation
    def categories(self, create, extracted, **kwargs):
        if create:
            if extracted is None:
                extracted = [CategoryFactory(type__plan=self.plan)]
            for category in extracted:
                self.categories.add(category)

    @post_generation
    def responsible_parties(self, create, extracted, **kwargs):
        if create:
            if extracted is None:
                extracted = [ActionResponsiblePartyFactory(action=self, organization=self.plan.organization)]
            for responsible_party in extracted:
                self.responsible_parties.add(responsible_party)


# FIXME: The factory name does not correspond to the model name because this would suggest that we build a Person
# object. We might want to consider renaming the model ActionContactPerson to ActionContact or similar.
class ActionContactFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionContactPerson'

    action = SubFactory(ActionFactory)
    person = SubFactory(PersonFactory)


class ActionResponsiblePartyFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionResponsibleParty'

    action = SubFactory(ActionFactory)
    organization = SubFactory(OrganizationFactory)
