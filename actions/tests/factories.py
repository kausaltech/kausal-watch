from __future__ import annotations

import typing
import datetime
from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import make_aware
from factory import LazyAttribute, SelfAttribute, Sequence, SubFactory, post_generation
from factory.django import DjangoModelFactory
from wagtail.core.rich_text import RichText
from wagtail_factories import StructBlockFactory

from aplans.factories import ModelFactory
import actions
from actions.models import AttributeType, Plan
from images.tests.factories import AplansImageFactory
from orgs.tests.factories import OrganizationFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory


class PlanFactory(ModelFactory[Plan]):
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
    published_at = make_aware(datetime.datetime(2021, 1, 1))

    @classmethod
    def _create(cls, model_class, *args, create_default_pages: bool = False, **kwargs) -> Plan:
        from actions.models.plan import set_default_page_creation

        with set_default_page_creation(create_default_pages):
            manager = cls._get_manager(model_class)
            obj = manager.create(*args, **kwargs)
        return obj


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


class CommonCategoryTypeFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CommonCategoryType'

    primary_language = 'en'
    identifier = Sequence(lambda i: f'cct{i}')
    name = Sequence(lambda i: f"Common category type {i}")


class CategoryTypeFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryType'

    plan = SubFactory(PlanFactory)
    identifier = Sequence(lambda i: f'ct{i}')
    name = Sequence(lambda i: f"Category type {i}")
    common = SubFactory(CommonCategoryTypeFactory)
    synchronize_with_pages = False


class AttributeTypeFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.AttributeType'
        exclude = ['scope']

    object_content_type = LazyAttribute(lambda _: ContentType.objects.get(app_label='actions', model='category'))
    scope = SubFactory(CategoryTypeFactory)
    scope_content_type = LazyAttribute(lambda o: ContentType.objects.get_for_model(o.scope))
    scope_id = SelfAttribute('scope.id')
    identifier = Sequence(lambda i: f'ctm{i}')
    name = Sequence(lambda i: f"Category attribute type {i}")
    format = AttributeType.AttributeFormat.RICH_TEXT


class AttributeTypeChoiceOptionFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.AttributeTypeChoiceOption'

    type = SubFactory(AttributeTypeFactory, format=AttributeType.AttributeFormat.ORDERED_CHOICE)
    identifier = Sequence(lambda i: f'ctmc{i}')
    name = Sequence(lambda i: f"Attribute type choice option {i}")


class CommonCategoryFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CommonCategory'

    type = SubFactory(CommonCategoryTypeFactory)
    identifier = Sequence(lambda i: f'categorytype{i}')
    name = Sequence(lambda i: f"Category type {i}")
    name_fi = Sequence(lambda i: f"Category type {i} (FI)")
    image = SubFactory(AplansImageFactory)


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.Category'

    type = SubFactory(CategoryTypeFactory)
    identifier = Sequence(lambda i: f'category{i}')
    name = Sequence(lambda i: f"Category {i}")
    name_fi = Sequence(lambda i: f"Category {i} (FI)")
    image = SubFactory(AplansImageFactory)
    common = SubFactory(CommonCategoryFactory)


class AttributeRichTextFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.AttributeRichText'
        exclude = ['content_object']

    type = SubFactory(AttributeTypeFactory, format=AttributeType.AttributeFormat.RICH_TEXT)
    content_type = LazyAttribute(lambda _: ContentType.objects.get(app_label='actions', model='category'))
    content_object = SubFactory(CategoryFactory)
    content_type = LazyAttribute(lambda o: ContentType.objects.get_for_model(o.content_object))
    object_id = SelfAttribute('content_object.id')
    text = Sequence(lambda i: f'AttributeRichText {i}')


class AttributeChoiceFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.AttributeChoice'
        exclude = ['content_object']

    type = SubFactory(AttributeTypeFactory, format=AttributeType.AttributeFormat.ORDERED_CHOICE)
    content_type = LazyAttribute(lambda _: ContentType.objects.get(app_label='actions', model='category'))
    content_object = SubFactory(CategoryFactory)
    content_type = LazyAttribute(lambda o: ContentType.objects.get_for_model(o.content_object))
    object_id = SelfAttribute('content_object.id')
    choice = SubFactory(AttributeTypeChoiceOptionFactory)


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
    description = "<p>Action description</p>"
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
