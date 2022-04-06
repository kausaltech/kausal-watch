import datetime
from factory import RelatedFactory, SelfAttribute, Sequence, SubFactory, post_generation
from factory.django import DjangoModelFactory
from wagtail.core.rich_text import RichText
from wagtail_factories import StructBlockFactory

import actions
from actions.models import CategoryAttributeType
from images.tests.factories import AplansImageFactory
from orgs.tests.factories import OrganizationFactory
from pages.tests.factories import CategoryPageFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory


class PlanFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.Plan'

    organization = SubFactory(OrganizationFactory)
    name = Sequence(lambda i: f"Plan {i}")
    identifier = Sequence(lambda i: f'plan{i}')
    image = SubFactory(AplansImageFactory)
    site_url = Sequence(lambda i: f'https://plan{i}.example.com')
    accessibility_statement_url = 'https://example.com'
    primary_language = 'en'
    other_languages = ['fi']


class PlanDomainFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.PlanDomain'

    plan = SubFactory(PlanFactory, _domain=None)
    hostname = Sequence(lambda i: f'plandomain{i}.example.org')


class ActionStatusFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionStatus'

    plan = SubFactory(PlanFactory)
    name = Sequence(lambda i: f"Action status {i}")
    identifier = Sequence(lambda i: f'action-status-{i}')


class ActionImplementationPhaseFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionImplementationPhase'

    plan = SubFactory(PlanFactory)
    name = Sequence(lambda i: f"Action implementation phase {i}")
    identifier = Sequence(lambda i: f'aip{i}')


class ActionScheduleFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionSchedule'

    plan = SubFactory(PlanFactory)
    name = "Test action schedule"
    begins_at = datetime.date(2020, 1, 1)
    ends_at = datetime.date(2021, 1, 1)


class ActionImpactFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionImpact'

    plan = SubFactory(PlanFactory)
    identifier = Sequence(lambda i: f'action-impact-{i}')
    name = Sequence(lambda i: f"Action impact {i}")


class CategoryTypeFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryType'

    plan = SubFactory(PlanFactory)
    identifier = Sequence(lambda i: f'ct{i}')
    name = Sequence(lambda i: f"Category type {i}")


class CategoryAttributeTypeFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryAttributeType'

    category_type = SubFactory(CategoryTypeFactory)
    identifier = Sequence(lambda i: f'ctm{i}')
    name = Sequence(lambda i: f"Category attribute type {i}")
    format = CategoryAttributeType.AttributeFormat.RICH_TEXT


class CategoryAttributeTypeChoiceOptionFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryAttributeTypeChoiceOption'

    type = SubFactory(CategoryAttributeTypeFactory, format=CategoryAttributeType.AttributeFormat.ORDERED_CHOICE)
    identifier = Sequence(lambda i: f'ctmc{i}')
    name = Sequence(lambda i: f"Category attribute type choice option {i}")


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.Category'

    type = SubFactory(CategoryTypeFactory)
    identifier = Sequence(lambda i: f'category{i}')
    name = Sequence(lambda i: f"Category {i}")
    image = SubFactory(AplansImageFactory)
    category_page = RelatedFactory(CategoryPageFactory,
                                   factory_related_name='category',
                                   parent=SelfAttribute('..type.plan.root_page'))


class CategoryAttributeRichTextFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryAttributeRichText'

    type = SubFactory(CategoryAttributeTypeFactory, format=CategoryAttributeType.AttributeFormat.RICH_TEXT)
    category = SubFactory(CategoryFactory)
    text = Sequence(lambda i: f'CategoryAttributeRichText {i}')


class CategoryAttributeChoiceFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryAttributeChoice'

    type = SubFactory(CategoryAttributeTypeFactory, format=CategoryAttributeType.AttributeFormat.ORDERED_CHOICE)
    category = SubFactory(CategoryFactory)
    choice = SubFactory(CategoryAttributeTypeChoiceOptionFactory)


class CategoryLevelFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryLevel'

    type = SubFactory(CategoryTypeFactory)
    name = Sequence(lambda i: f"Category level name {i}")
    name_plural = Sequence(lambda i: f'Category level name plural {i}')


class ScenarioFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.Scenario'

    plan = SubFactory(PlanFactory)
    name = Sequence(lambda i: f"Scenario {i}")
    identifier = Sequence(lambda i: f'scenario{i}')
    description = "Scenario description"


class ActionStatusUpdateFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionStatusUpdate'

    action = SubFactory('actions.tests.factories.ActionFactory')
    title = "Action status update"
    date = datetime.date(2020, 1, 1)
    author = SubFactory(PersonFactory)
    content = "Action status update content"
    # created_at = None  # Should be set automatically
    # modified_at = None  # Should be set automatically
    created_by = SubFactory(UserFactory)


class ImpactGroupFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ImpactGroup'

    plan = SubFactory(PlanFactory)
    name = Sequence(lambda i: f"Impact group {i}")
    identifier = Sequence(lambda i: f'impact-group-{i}')
    parent = None
    weight = 1.0
    color = 'red'


class MonitoringQualityPointFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.MonitoringQualityPoint'

    name = Sequence(lambda i: f"Monitoring quality point {i}")
    description_yes = "Yes"
    description_no = "No"
    plan = SubFactory(PlanFactory)
    identifier = Sequence(lambda i: f'monitoring-quality-point-{i}')


class ActionFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.Action'

    plan = SubFactory(PlanFactory)
    name = Sequence(lambda i: f"Action {i}")
    identifier = Sequence(lambda i: f'action{i}')
    official_name = name
    image = SubFactory(AplansImageFactory)
    description = "Action description"
    impact = SubFactory(ActionImpactFactory, plan=SelfAttribute('..plan'))
    status = SubFactory(ActionStatusFactory, plan=SelfAttribute('..plan'))
    implementation_phase = SubFactory(ActionImplementationPhaseFactory, plan=SelfAttribute('..plan'))
    manual_status = True
    manual_status_reason = "Because this is a test."
    completion = 99

    @post_generation
    def categories(obj, create, extracted, **kwargs):
        if create and extracted:
            for category in extracted:
                obj.categories.add(category)

    @post_generation
    def monitoring_quality_points(obj, create, extracted, **kwargs):
        if create and extracted:
            for monitoring_quality_point in extracted:
                obj.monitoring_quality_points.add(monitoring_quality_point)

    @post_generation
    def schedule(obj, create, extracted, **kwargs):
        if create and extracted:
            for schedule in extracted:
                obj.schedule.add(schedule)


class ActionTaskFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionTask'

    action = SubFactory(ActionFactory)
    name = Sequence(lambda i: f"Action task {i}")
    state = actions.models.ActionTask.NOT_STARTED
    comment = "Comment"
    due_at = datetime.date(2020, 1, 1)
    completed_at = None
    completed_by = None
    # created_at = None  # Should be set automatically
    # modified_at = None  # Should be set automatically


class ImpactGroupActionFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ImpactGroupAction'

    group = SubFactory(ImpactGroupFactory)
    action = SubFactory(ActionFactory, plan=SelfAttribute('..group.plan'))
    impact = SubFactory(ActionImpactFactory, plan=SelfAttribute('..group.plan'))


class ActionResponsiblePartyFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionResponsibleParty'

    action = SubFactory(ActionFactory)
    organization = SubFactory(OrganizationFactory)


# FIXME: The factory name does not correspond to the model name because this would suggest that we build a Person
# object. We might want to consider renaming the model ActionContactPerson to ActionContact or similar.
class ActionContactFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.ActionContactPerson'

    action = SubFactory(ActionFactory)
    person = SubFactory(PersonFactory, organization=SelfAttribute('..action.plan.organization'))


class ActionListBlockFactory(StructBlockFactory):
    class Meta:
        model = actions.blocks.ActionListBlock

    category_filter = SubFactory(CategoryFactory)


class CategoryListBlockFactory(StructBlockFactory):
    class Meta:
        model = actions.blocks.CategoryListBlock

    heading = "Category list heading"
    lead = RichText("<p>Category list lead</p>")
    style = 'cards'
