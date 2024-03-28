from __future__ import annotations

import datetime
import factory
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.utils.timezone import make_aware
from factory import LazyAttribute, RelatedFactory, SelfAttribute, Sequence, SubFactory, post_generation
from wagtail.models import Workflow, WorkflowTask, Task as WagtailTask
from wagtail.models.i18n import Locale
from wagtail.rich_text import RichText
from wagtail.test.utils.wagtail_factories import StructBlockFactory

from actions.blocks import ActionListBlock, CategoryListBlock
from actions.models import (
    Action, ActionContactPerson, ActionImpact, ActionImplementationPhase, ActionLink, ActionSchedule, ActionStatus,
    ActionStatusUpdate, ActionTask, ActionResponsibleParty, AttributeCategoryChoice, AttributeChoice,
    AttributeChoiceWithText, AttributeNumericValue, AttributeRichText, AttributeText, AttributeType,
    AttributeTypeChoiceOption, Category, CategoryLevel, CategoryType, CommonCategory, CommonCategoryType, ImpactGroup,
    ImpactGroupAction, MonitoringQualityPoint, Plan, PlanDomain, PlanFeatures, Scenario
)
from aplans.factories import ModelFactory
from images.tests.factories import AplansImageFactory
from orgs.tests.factories import OrganizationFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory


@factory.django.mute_signals(post_save)
class PlanFactory(ModelFactory[Plan]):
    organization = SubFactory(OrganizationFactory)
    name = Sequence(lambda i: f"Plan {i}")
    identifier = Sequence(lambda i: f'plan{i}')
    image = SubFactory(AplansImageFactory)
    site_url = Sequence(lambda i: f'https://plan{i}.example.com')
    accessibility_statement_url = 'https://example.com'
    primary_language = 'en'
    other_languages = ['fi']
    published_at = make_aware(datetime.datetime(2021, 1, 1))
    general_content = RelatedFactory('content.tests.factories.SiteGeneralContentFactory', factory_related_name='plan')
    features = RelatedFactory('actions.tests.factories.PlanFeaturesFactory', factory_related_name='plan')
    notification_settings = RelatedFactory(
        'notifications.tests.factories.NotificationSettingsFactory', factory_related_name='plan'
    )

    @classmethod
    def _create(cls, model_class, *args, **kwargs) -> Plan:
        Locale.objects.get_or_create(language_code=kwargs['primary_language'])
        for language in kwargs.get('other_languages', []):
            Locale.objects.get_or_create(language_code=language)
        return super()._create(model_class, *args, **kwargs)


@factory.django.mute_signals(post_save)
class PlanFeaturesFactory(ModelFactory[PlanFeatures]):
    plan = SubFactory(PlanFactory, features=None)


class PlanDomainFactory(ModelFactory[PlanDomain]):
    plan = SubFactory(PlanFactory, _domain=None)
    hostname = Sequence(lambda i: f'plandomain{i}.example.org')


class ActionStatusFactory(ModelFactory[ActionStatus]):
    plan = SubFactory(PlanFactory)
    name = Sequence(lambda i: f"Action status {i}")
    identifier = Sequence(lambda i: f'action-status-{i}')


class ActionImplementationPhaseFactory(ModelFactory[ActionImplementationPhase]):
    plan = SubFactory(PlanFactory)
    name = Sequence(lambda i: f"Action implementation phase {i}")
    identifier = Sequence(lambda i: f'aip{i}')


class ActionScheduleFactory(ModelFactory[ActionSchedule]):
    plan = SubFactory(PlanFactory)
    name = "Test action schedule"
    begins_at = datetime.date(2020, 1, 1)
    ends_at = datetime.date(2021, 1, 1)


class ActionImpactFactory(ModelFactory[ActionImpact]):
    plan = SubFactory(PlanFactory)
    identifier = Sequence(lambda i: f'action-impact-{i}')
    name = Sequence(lambda i: f"Action impact {i}")


class ActionLinkFactory(ModelFactory[ActionLink]):
    action = SubFactory('actions.tests.factories.ActionFactory')
    url = Sequence(lambda i: f'https://plan{i}.example.com')
    title = "Action link"


class CommonCategoryTypeFactory(ModelFactory[CommonCategoryType]):
    primary_language = 'en'
    identifier = Sequence(lambda i: f'cct{i}')
    name = Sequence(lambda i: f"Common category type {i}")
    lead_paragraph = "foo"
    help_text = "bar"


class CategoryTypeFactory(ModelFactory[CategoryType]):
    plan = SubFactory(PlanFactory)
    identifier = Sequence(lambda i: f'ct{i}')
    name = Sequence(lambda i: f"Category type {i}")
    lead_paragraph = "foo"
    help_text = "bar"
    common = SubFactory(CommonCategoryTypeFactory)
    synchronize_with_pages = False


class AttributeTypeFactory(ModelFactory[AttributeType]):
    class Meta:
        exclude = ['scope']

    object_content_type = LazyAttribute(lambda _: ContentType.objects.get_for_model(Category))
    scope = SubFactory(CategoryTypeFactory)
    scope_content_type = LazyAttribute(lambda o: ContentType.objects.get_for_model(o.scope))
    scope_id = SelfAttribute('scope.id')
    identifier = Sequence(lambda i: f'ctm{i}')
    name = Sequence(lambda i: f"Category attribute type {i}")
    help_text = "foo"
    format = AttributeType.AttributeFormat.RICH_TEXT
    unit = None
    attribute_category_type = None
    show_choice_names = True
    has_zero_option = False


class AttributeTypeChoiceOptionFactory(ModelFactory[AttributeTypeChoiceOption]):
    type = SubFactory(AttributeTypeFactory, format=AttributeType.AttributeFormat.ORDERED_CHOICE)
    identifier = Sequence(lambda i: f'ctmc{i}')
    name = Sequence(lambda i: f"Attribute type choice option {i}")


class CommonCategoryFactory(ModelFactory[CommonCategory]):
    type = SubFactory(CommonCategoryTypeFactory)
    identifier = Sequence(lambda i: f'categorytype{i}')
    name = Sequence(lambda i: f"Category type {i}")
    name_fi = Sequence(lambda i: f"Category type {i} (FI)")
    image = SubFactory(AplansImageFactory)
    lead_paragraph = "foo"
    help_text = "bar"


class CategoryFactory(ModelFactory[Category]):
    type = SubFactory(CategoryTypeFactory)
    identifier = Sequence(lambda i: f'category{i}')
    name = Sequence(lambda i: f"Category {i}")
    name_fi = Sequence(lambda i: f"Category {i} (FI)")
    image = SubFactory(AplansImageFactory)
    common = SubFactory(CommonCategoryFactory)
    lead_paragraph = "foo"
    help_text = "bar"


class AttributeCategoryChoiceFactory(ModelFactory[AttributeCategoryChoice]):
    class Meta:
        exclude = ['content_object']

    type = SubFactory(AttributeTypeFactory, format=AttributeType.AttributeFormat.CATEGORY_CHOICE)
    content_object = SubFactory(CategoryFactory)
    content_type = LazyAttribute(lambda o: ContentType.objects.get_for_model(o.content_object))
    object_id = SelfAttribute('content_object.id')

    @post_generation
    def categories(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for category in extracted:
                self.categories.add(category)


class AttributeTextFactory(ModelFactory[AttributeText]):
    class Meta:
        exclude = ['content_object']

    type = SubFactory(AttributeTypeFactory, format=AttributeType.AttributeFormat.TEXT)
    content_object = SubFactory(CategoryFactory)
    content_type = LazyAttribute(lambda o: ContentType.objects.get_for_model(o.content_object))
    object_id = SelfAttribute('content_object.id')
    text = Sequence(lambda i: f'AttributeText {i}')


class AttributeNumericValueFactory(ModelFactory[AttributeNumericValue]):
    class Meta:
        exclude = ['content_object']

    type = SubFactory(AttributeTypeFactory, format=AttributeType.AttributeFormat.NUMERIC)
    content_object = SubFactory(CategoryFactory)
    content_type = LazyAttribute(lambda o: ContentType.objects.get_for_model(o.content_object))
    object_id = SelfAttribute('content_object.id')
    value = Sequence(lambda i: float(i/100))


class AttributeRichTextFactory(ModelFactory[AttributeRichText]):
    class Meta:
        exclude = ['content_object']

    type = SubFactory(AttributeTypeFactory, format=AttributeType.AttributeFormat.RICH_TEXT)
    content_object = SubFactory(CategoryFactory)
    content_type = LazyAttribute(lambda o: ContentType.objects.get_for_model(o.content_object))
    object_id = SelfAttribute('content_object.id')
    text = Sequence(lambda i: f'AttributeRichText {i}')


class AttributeChoiceFactory(ModelFactory[AttributeChoice]):
    class Meta:
        exclude = ['content_object']

    type = SubFactory(AttributeTypeFactory, format=AttributeType.AttributeFormat.ORDERED_CHOICE)
    content_object = SubFactory(CategoryFactory)
    content_type = LazyAttribute(lambda o: ContentType.objects.get_for_model(o.content_object))
    object_id = SelfAttribute('content_object.id')
    choice = SubFactory(AttributeTypeChoiceOptionFactory)


class AttributeChoiceWithTextFactory(ModelFactory[AttributeChoiceWithText]):
    class Meta:
        exclude = ['content_object']

    type = SubFactory(AttributeTypeFactory, format=AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT)
    content_object = SubFactory(CategoryFactory)
    content_type = LazyAttribute(lambda o: ContentType.objects.get_for_model(o.content_object))
    object_id = SelfAttribute('content_object.id')
    choice = SubFactory(AttributeTypeChoiceOptionFactory)
    text = Sequence(lambda i: f'AttributeChoiceText {i}')


class CategoryLevelFactory(ModelFactory[CategoryLevel]):
    type = SubFactory(CategoryTypeFactory)
    name = Sequence(lambda i: f"Category level name {i}")
    name_plural = Sequence(lambda i: f'Category level name plural {i}')


class ScenarioFactory(ModelFactory[Scenario]):
    plan = SubFactory(PlanFactory)
    name = Sequence(lambda i: f"Scenario {i}")
    identifier = Sequence(lambda i: f'scenario{i}')
    description = "Scenario description"


class ActionStatusUpdateFactory(ModelFactory[ActionStatusUpdate]):
    action = SubFactory('actions.tests.factories.ActionFactory')
    title = "Action status update"
    date = datetime.date(2020, 1, 1)
    author = SubFactory(PersonFactory)
    content = "Action status update content"
    # created_at = None  # Should be set automatically
    # modified_at = None  # Should be set automatically
    created_by = SubFactory(UserFactory)


class ImpactGroupFactory(ModelFactory[ImpactGroup]):
    plan = SubFactory(PlanFactory)
    name = Sequence(lambda i: f"Impact group {i}")
    identifier = Sequence(lambda i: f'impact-group-{i}')
    parent = None
    weight = 1.0
    color = 'red'


class MonitoringQualityPointFactory(ModelFactory[MonitoringQualityPoint]):
    name = Sequence(lambda i: f"Monitoring quality point {i}")
    description_yes = "Yes"
    description_no = "No"
    plan = SubFactory(PlanFactory)
    identifier = Sequence(lambda i: f'monitoring-quality-point-{i}')


class ActionFactory(ModelFactory[Action]):
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


class ActionTaskFactory(ModelFactory[ActionTask]):
    action = SubFactory(ActionFactory)
    name = Sequence(lambda i: f"Action task {i}")
    state = ActionTask.NOT_STARTED
    comment = "Comment"
    due_at = datetime.date(2020, 1, 1)
    completed_at = None
    completed_by = None
    # created_at = None  # Should be set automatically
    # modified_at = None  # Should be set automatically


class ImpactGroupActionFactory(ModelFactory[ImpactGroupAction]):
    group = SubFactory(ImpactGroupFactory)
    action = SubFactory(ActionFactory, plan=SelfAttribute('..group.plan'))
    impact = SubFactory(ActionImpactFactory, plan=SelfAttribute('..group.plan'))


class ActionResponsiblePartyFactory(ModelFactory[ActionResponsibleParty]):
    action = SubFactory(ActionFactory)
    organization = SubFactory(OrganizationFactory)
    role = ActionResponsibleParty.Role.PRIMARY
    specifier = "foo"


# FIXME: The factory name does not correspond to the model name because this would suggest that we build a Person
# object. We might want to consider renaming the model ActionContactPerson to ActionContact or similar.
class ActionContactFactory(ModelFactory[ActionContactPerson]):
    action = SubFactory(ActionFactory)
    person = SubFactory(PersonFactory, organization=SelfAttribute('..action.plan.organization'))
    role = ActionContactPerson.Role.MODERATOR


class ActionListBlockFactory(StructBlockFactory):
    class Meta:
        model = ActionListBlock

    category_filter = SubFactory(CategoryFactory)


class CategoryListBlockFactory(StructBlockFactory):
    class Meta:
        model = CategoryListBlock

    heading = "Category list heading"
    lead = RichText("<p>Category list lead</p>")
    style = 'cards'


class WagtailTaskFactory(ModelFactory[WagtailTask]):
    class Meta:
        model = WagtailTask

    name = Sequence(lambda i: f'WorkflowTask {i}')
    active = True


class WorkflowFactory(ModelFactory[Workflow]):
    class Meta:
        model = Workflow

    name = Sequence(lambda i: f'Workflow {i}')
    active = True


class WorkflowTaskFactory(ModelFactory[WorkflowTask]):
    class Meta:
        model = WorkflowTask

    workflow = SubFactory(WorkflowFactory)
    task = SubFactory(WagtailTaskFactory)
