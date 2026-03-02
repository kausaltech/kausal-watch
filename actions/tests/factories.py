from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.utils.timezone import make_aware
from wagtail.models import Task as WagtailTask, Workflow, WorkflowTask
from wagtail.models.i18n import Locale
from wagtail.rich_text import RichText
from wagtail.test.utils.wagtail_factories import StructBlockFactory
from wagtail.test.utils.wagtail_factories.blocks import BlockFactory

import factory
from factory.declarations import LazyAttribute, RelatedFactory, SelfAttribute, Sequence, SubFactory
from factory.helpers import post_generation

from aplans.factories import ModelFactory

from actions.blocks.action_list import ActionListBlock
from actions.blocks.category_list import CategoryListBlock
from actions.blocks.category_page_layout import CategoryPageAttributeTypeBlock, CategoryPageProgressBlock
from actions.blocks.choosers import AttributeTypeChooserBlock
from actions.models import (
    Action,
    ActionContactPerson,
    ActionImpact,
    ActionImplementationPhase,
    ActionLink,
    ActionResponsibleParty,
    ActionSchedule,
    ActionStatus,
    ActionStatusUpdate,
    ActionTask,
    AttributeCategoryChoice,
    AttributeChoice,
    AttributeChoiceWithText,
    AttributeNumericValue,
    AttributeRichText,
    AttributeText,
    AttributeType,
    AttributeTypeChoiceOption,
    Category,
    CategoryLevel,
    CategoryType,
    CommonCategory,
    CommonCategoryType,
    ImpactGroup,
    ImpactGroupAction,
    MonitoringQualityPoint,
    Plan,
    PlanDomain,
    PlanFeatures,
    Pledge,
    Scenario,
)
from actions.models.action_deps import ActionDependencyRelationship, ActionDependencyRole
from content.models import SiteGeneralContent
from images.models import AplansImage
from images.tests.factories import AplansImageFactory
from notifications.models import NotificationSettings
from orgs.models import Organization
from orgs.tests.factories import OrganizationFactory
from people.models import Person
from people.tests.factories import PersonFactory
from users.models import User
from users.tests.factories import UserFactory

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.dispatch.dispatcher import Signal

    from indicators.models import Unit

    def mute_signals[X](signal: Signal) -> Callable[[X], X]: ...
else:
    mute_signals = factory.django.mute_signals


@mute_signals(post_save)
class PlanFactory(ModelFactory[Plan]):
    organization = SubFactory[Plan, Organization](OrganizationFactory)
    name = Sequence(lambda i: f'Plan {i}')
    identifier = Sequence(lambda i: f'plan{i}')
    image = SubFactory[Plan, AplansImage](AplansImageFactory)
    site_url = Sequence(lambda i: f'https://plan{i}.example.com')
    accessibility_statement_url = 'https://example.com'
    primary_language = 'en'
    other_languages = ['fi']
    published_at = make_aware(datetime.datetime(2021, 1, 1))  # noqa: DTZ001
    general_content = RelatedFactory[Plan, SiteGeneralContent](
        'content.tests.factories.SiteGeneralContentFactory', factory_related_name='plan'
    )
    features = RelatedFactory[Plan, PlanFeatures]('actions.tests.factories.PlanFeaturesFactory', factory_related_name='plan')
    notification_settings = RelatedFactory[Plan, NotificationSettings](
        'notifications.tests.factories.NotificationSettingsFactory',
        factory_related_name='plan',
    )
    kausal_paths_instance_uuid = 'paths_uuid'

    class Meta:
        skip_postgeneration_save = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs) -> Plan:
        Locale.objects.get_or_create(language_code=kwargs['primary_language'])
        for language in kwargs.get('other_languages', []):
            Locale.objects.get_or_create(language_code=language)
        return super()._create(model_class, *args, **kwargs)

    if TYPE_CHECKING:

        @classmethod
        def create(cls, *args, **kwargs) -> Plan: ...


@mute_signals(post_save)
class PlanFeaturesFactory(ModelFactory[PlanFeatures]):
    plan = SubFactory[PlanFeatures, Plan](PlanFactory, features=None)


@mute_signals(post_save)
class PlanDomainFactory(ModelFactory[PlanDomain]):
    plan = SubFactory[PlanDomain, Plan](PlanFactory, _domain=None)
    hostname = Sequence(lambda i: f'plandomain{i}.example.org')
    redirect_to_hostname = ''


class ActionDependencyRoleFactory(ModelFactory[ActionDependencyRole]):
    plan = SubFactory[ActionDependencyRole, Plan](PlanFactory)
    name = Sequence(lambda i: f'Action dependency role {i}')
    order = Sequence(lambda i: i)


class ActionStatusFactory(ModelFactory[ActionStatus]):
    plan = SubFactory[ActionStatus, Plan](PlanFactory)
    name = Sequence(lambda i: f'Action status {i}')
    identifier = Sequence(lambda i: f'action-status-{i}')


class ActionImplementationPhaseFactory(ModelFactory[ActionImplementationPhase]):
    plan = SubFactory[ActionImplementationPhase, Plan](PlanFactory)
    name = Sequence(lambda i: f'Action implementation phase {i}')
    identifier = Sequence(lambda i: f'aip{i}')


class ActionScheduleFactory(ModelFactory[ActionSchedule]):
    plan = SubFactory[ActionSchedule, Plan](PlanFactory)
    name = 'Test action schedule'
    begins_at = datetime.date(2020, 1, 1)
    ends_at = datetime.date(2021, 1, 1)


class ActionImpactFactory(ModelFactory[ActionImpact]):
    plan = SubFactory[ActionImpact, Plan](PlanFactory)
    identifier = Sequence(lambda i: f'action-impact-{i}')
    name = Sequence(lambda i: f'Action impact {i}')


class ActionLinkFactory(ModelFactory[ActionLink]):
    action = SubFactory[ActionLink, Action]('actions.tests.factories.ActionFactory')
    url = Sequence(lambda i: f'https://plan{i}.example.com')
    title = 'Action link'


class CommonCategoryTypeFactory(ModelFactory[CommonCategoryType]):
    primary_language = 'en'
    identifier = Sequence(lambda i: f'cct{i}')
    name = Sequence(lambda i: f'Common category type {i}')
    lead_paragraph = 'foo'
    help_text = 'bar'


class CategoryTypeFactory(ModelFactory[CategoryType]):
    plan = SubFactory[CategoryType, Plan](PlanFactory)
    identifier = Sequence(lambda i: f'ct{i}')
    name = Sequence(lambda i: f'Category type {i}')
    lead_paragraph = 'foo'
    help_text = 'bar'
    common = SubFactory[CategoryType, CommonCategoryType](CommonCategoryTypeFactory)
    synchronize_with_pages = False


class AttributeTypeFactory(ModelFactory[AttributeType]):
    class Meta:
        exclude = ['scope']

    object_content_type = LazyAttribute[AttributeType, ContentType](lambda _: ContentType.objects.get_for_model(Category))
    scope = SubFactory[AttributeType, CategoryType](CategoryTypeFactory)
    scope_content_type = LazyAttribute[AttributeType, ContentType](lambda o: ContentType.objects.get_for_model(o.scope))
    scope_id = SelfAttribute[AttributeType, int]('scope.id')
    identifier = Sequence(lambda i: f'ctm{i}')
    name = Sequence(lambda i: f'Category attribute type {i}')
    help_text = 'foo'
    format: AttributeType.AttributeFormat = AttributeType.AttributeFormat.RICH_TEXT
    unit: Unit | None = None
    attribute_category_type: CategoryType | None = None
    show_choice_names = True
    has_zero_option = False


class AttributeTypeChoiceOptionFactory(ModelFactory[AttributeTypeChoiceOption]):
    type = SubFactory[AttributeTypeChoiceOption, AttributeType](
        AttributeTypeFactory, format=AttributeType.AttributeFormat.ORDERED_CHOICE
    )
    identifier = Sequence(lambda i: f'ctmc{i}')
    name = Sequence(lambda i: f'Attribute type choice option {i}')


class CommonCategoryFactory(ModelFactory[CommonCategory]):
    type = SubFactory[CommonCategory, CommonCategoryType](CommonCategoryTypeFactory)
    identifier = Sequence(lambda i: f'categorytype{i}')
    name = Sequence(lambda i: f'Category type {i}')
    name_fi = Sequence(lambda i: f'Category type {i} (FI)')
    image = SubFactory[CommonCategory, AplansImage](AplansImageFactory)
    lead_paragraph = 'foo'
    help_text = 'bar'


class CategoryFactory(ModelFactory[Category]):
    type = SubFactory[Category, CategoryType](CategoryTypeFactory)
    identifier = Sequence(lambda i: f'category{i}')
    name = Sequence(lambda i: f'Category {i}')
    name_fi = Sequence(lambda i: f'Category {i} (FI)')
    image = SubFactory[Category, AplansImage](AplansImageFactory)
    common = SubFactory[Category, CommonCategory](CommonCategoryFactory)
    lead_paragraph = 'foo'
    help_text = 'bar'
    kausal_paths_node_uuid = 'kausal_paths_node_uuid'


class AttributeCategoryChoiceFactory(ModelFactory[AttributeCategoryChoice]):
    class Meta:
        exclude = ['content_object']
        skip_postgeneration_save = True

    type = SubFactory[AttributeCategoryChoice, AttributeType](
        AttributeTypeFactory, format=AttributeType.AttributeFormat.CATEGORY_CHOICE
    )
    content_object = SubFactory[AttributeCategoryChoice, Category](CategoryFactory)
    content_type = LazyAttribute[AttributeCategoryChoice, ContentType](
        lambda o: ContentType.objects.get_for_model(o.content_object)
    )
    object_id = SelfAttribute[AttributeCategoryChoice, int]('content_object.id')

    @post_generation
    @staticmethod
    def categories(obj: AttributeCategoryChoice, create: bool, extracted: list[Category]) -> None:
        if not create:
            return
        if extracted:
            for category in extracted:
                obj.categories.add(category)
            obj.save()


class AttributeTextFactory(ModelFactory[AttributeText]):
    class Meta:
        exclude = ['content_object']

    type = SubFactory[AttributeText, AttributeType](AttributeTypeFactory, format=AttributeType.AttributeFormat.TEXT)
    content_object = SubFactory[AttributeText, Category](CategoryFactory)
    content_type = LazyAttribute[AttributeText, ContentType](lambda o: ContentType.objects.get_for_model(o.content_object))
    object_id = SelfAttribute[AttributeText, int]('content_object.id')
    text = Sequence(lambda i: f'AttributeText {i}')


class AttributeNumericValueFactory(ModelFactory[AttributeNumericValue]):
    class Meta:
        exclude = ['content_object']

    type = SubFactory[AttributeNumericValue, AttributeType](AttributeTypeFactory, format=AttributeType.AttributeFormat.NUMERIC)
    content_object = SubFactory[AttributeNumericValue, Category](CategoryFactory)
    content_type = LazyAttribute[AttributeNumericValue, ContentType](
        lambda o: ContentType.objects.get_for_model(o.content_object)
    )
    object_id = SelfAttribute[AttributeNumericValue, int]('content_object.id')
    value = Sequence(lambda i: float(i / 100))


class AttributeRichTextFactory(ModelFactory[AttributeRichText]):
    class Meta:
        exclude = ['content_object']

    type = SubFactory[AttributeRichText, AttributeType](AttributeTypeFactory, format=AttributeType.AttributeFormat.RICH_TEXT)
    content_object = SubFactory[AttributeRichText, Category](CategoryFactory)
    content_type = LazyAttribute[AttributeRichText, ContentType](lambda o: ContentType.objects.get_for_model(o.content_object))
    object_id = SelfAttribute[AttributeRichText, int]('content_object.id')
    text = Sequence(lambda i: f'AttributeRichText {i}')


class AttributeChoiceFactory(ModelFactory[AttributeChoice]):
    class Meta:
        exclude = ['content_object']

    type = SubFactory[AttributeChoice, AttributeType](AttributeTypeFactory, format=AttributeType.AttributeFormat.ORDERED_CHOICE)
    content_object = SubFactory[AttributeChoice, Category](CategoryFactory)
    content_type = LazyAttribute[AttributeChoice, ContentType](lambda o: ContentType.objects.get_for_model(o.content_object))
    object_id = SelfAttribute[AttributeChoice, int]('content_object.id')
    choice = SubFactory[AttributeChoice, AttributeTypeChoiceOption](AttributeTypeChoiceOptionFactory)


class AttributeChoiceWithTextFactory(ModelFactory[AttributeChoiceWithText]):
    class Meta:
        exclude = ['content_object']

    type = SubFactory[AttributeChoiceWithText, AttributeType](
        AttributeTypeFactory, format=AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT
    )
    content_object = SubFactory[AttributeChoiceWithText, Category](CategoryFactory)
    content_type = LazyAttribute[AttributeChoiceWithText, ContentType](
        lambda o: ContentType.objects.get_for_model(o.content_object)
    )
    object_id = SelfAttribute[AttributeChoiceWithText, int]('content_object.id')
    choice = SubFactory[AttributeChoiceWithText, AttributeTypeChoiceOption](AttributeTypeChoiceOptionFactory)
    text = Sequence(lambda i: f'AttributeChoiceText {i}')


class CategoryLevelFactory(ModelFactory[CategoryLevel]):
    type = SubFactory[CategoryLevel, CategoryType](CategoryTypeFactory)
    name = Sequence(lambda i: f'Category level name {i}')
    name_plural = Sequence(lambda i: f'Category level name plural {i}')


class ScenarioFactory(ModelFactory[Scenario]):
    plan = SubFactory[Scenario, Plan](PlanFactory)
    name = Sequence(lambda i: f'Scenario {i}')
    identifier = Sequence(lambda i: f'scenario{i}')
    description = 'Scenario description'


class ActionStatusUpdateFactory(ModelFactory[ActionStatusUpdate]):
    action = SubFactory[ActionStatusUpdate, Action]('actions.tests.factories.ActionFactory')
    title = 'Action status update'
    date = datetime.date(2020, 1, 1)
    author = SubFactory[ActionStatusUpdate, Person](PersonFactory)
    content = 'Action status update content'
    created_by = SubFactory[ActionStatusUpdate, User](UserFactory)


class ImpactGroupFactory(ModelFactory[ImpactGroup]):
    plan = SubFactory[ImpactGroup, Plan](PlanFactory)
    name = Sequence(lambda i: f'Impact group {i}')
    identifier = Sequence(lambda i: f'impact-group-{i}')
    parent: ImpactGroup | None = None
    weight = 1.0
    color = 'red'


class MonitoringQualityPointFactory(ModelFactory[MonitoringQualityPoint]):
    name = Sequence(lambda i: f'Monitoring quality point {i}')
    description_yes = 'Yes'
    description_no = 'No'
    plan = SubFactory[MonitoringQualityPoint, Plan](PlanFactory)
    identifier = Sequence(lambda i: f'monitoring-quality-point-{i}')


class ActionFactory(ModelFactory[Action]):
    plan = SubFactory[Action, Plan](PlanFactory)
    name = Sequence(lambda i: f'Action {i}')
    identifier = Sequence(lambda i: f'action{i}')
    official_name = name
    image = SubFactory[Action, AplansImage](AplansImageFactory)
    description = '<p>Action description</p>'
    impact = SubFactory[Action, ActionImpact](ActionImpactFactory, plan=SelfAttribute('..plan'))
    status = SubFactory[Action, ActionStatus](ActionStatusFactory, plan=SelfAttribute('..plan'))
    implementation_phase = SubFactory[Action, ActionImplementationPhase](
        ActionImplementationPhaseFactory, plan=SelfAttribute('..plan')
    )
    manual_status = True
    manual_status_reason = 'Because this is a test.'
    completion = 99

    class Meta:
        skip_postgeneration_save = True

    @post_generation
    @staticmethod
    def categories(obj: Action, create: bool, extracted: list[Category]) -> None:
        if create and extracted:
            for category in extracted:
                obj.categories.add(category)
            obj.save()

    @post_generation
    @staticmethod
    def monitoring_quality_points(obj: Action, create: bool, extracted: list[MonitoringQualityPoint]) -> None:
        if create and extracted:
            for monitoring_quality_point in extracted:
                obj.monitoring_quality_points.add(monitoring_quality_point)
            obj.save()

    @post_generation
    @staticmethod
    def schedule(obj: Action, create: bool, extracted: list[ActionSchedule]) -> None:
        if create and extracted:
            for schedule in extracted:
                obj.schedule.add(schedule)
            obj.save()


class ActionTaskFactory(ModelFactory[ActionTask]):
    action = SubFactory[ActionTask, Action](ActionFactory)
    name = Sequence(lambda i: f'Action task {i}')
    state = ActionTask.NOT_STARTED
    details = "Comment"
    due_at = datetime.date(2020, 1, 1)
    completed_at: datetime.date | None = None
    completed_by: Person | None = None
    # created_at = None  # Should be set automatically
    # modified_at = None  # Should be set automatically


class ImpactGroupActionFactory(ModelFactory[ImpactGroupAction]):
    group = SubFactory[ImpactGroupAction, ImpactGroup](ImpactGroupFactory)
    action = SubFactory[ImpactGroupAction, Action](ActionFactory, plan=SelfAttribute('..group.plan'))
    impact = SubFactory[ImpactGroupAction, ActionImpact](ActionImpactFactory, plan=SelfAttribute('..group.plan'))


class ActionResponsiblePartyFactory(ModelFactory[ActionResponsibleParty]):
    action = SubFactory[ActionResponsibleParty, Action](ActionFactory)
    organization = SubFactory[ActionResponsibleParty, Organization](OrganizationFactory)
    role = ActionResponsibleParty.Role.PRIMARY
    specifier = 'foo'


# FIXME: The factory name does not correspond to the model name because this would suggest that we build a Person
# object. We might want to consider renaming the model ActionContactPerson to ActionContact or similar.
class ActionContactFactory(ModelFactory[ActionContactPerson]):
    action = SubFactory[ActionContactPerson, Action](ActionFactory)
    person = SubFactory[ActionContactPerson, Person](PersonFactory, organization=SelfAttribute('..action.plan.organization'))
    role = ActionContactPerson.Role.MODERATOR


class ActionDependencyRelationshipFactory(ModelFactory[ActionDependencyRelationship]):
    preceding = SubFactory[ActionDependencyRelationship, Action](ActionFactory)
    dependent = SubFactory[ActionDependencyRelationship, Action](ActionFactory, plan=SelfAttribute('..preceding.plan'))


class ActionListBlockFactory(StructBlockFactory):
    class Meta:
        model = ActionListBlock

    category_filter = SubFactory[ActionListBlock, Category](CategoryFactory)


class CategoryListBlockFactory(StructBlockFactory):
    class Meta:
        model = CategoryListBlock

    heading = 'Category list heading'
    lead = RichText('<p>Category list lead</p>')
    style = 'cards'


class AttributeTypeChooserBlockFactory(BlockFactory):
    class Meta:
        model = AttributeTypeChooserBlock

    value = SubFactory[AttributeTypeChooserBlock, AttributeType]('actions.tests.factories.AttributeTypeFactory')


class CategoryPageAttributeTypeBlockFactory(StructBlockFactory):
    class Meta:
        model = CategoryPageAttributeTypeBlock

    attribute_type = SubFactory[CategoryPageAttributeTypeBlock, AttributeTypeChooserBlock](AttributeTypeChooserBlockFactory)


class CategoryPageProgressBlockFactory(StructBlockFactory):
    class Meta:
        model = CategoryPageProgressBlock

    basis = 'implementation_phase'


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

    workflow = SubFactory[WorkflowTask, Workflow](WorkflowFactory)
    task = SubFactory[WorkflowTask, WagtailTask](WagtailTaskFactory)


@mute_signals(post_save)
class PledgeFactory(ModelFactory[Pledge]):
    plan = SubFactory[Pledge, Plan](PlanFactory)
    name = Sequence(lambda i: f'Pledge {i}')
    slug = Sequence(lambda i: f'pledge-{i}')
    description = 'A test pledge description'
    resident_count = 100
    impact_statement = 'We save 100kg CO₂e each year.'
    local_equivalency = "That's equivalent to 10 round trips."

    class Meta:
        skip_postgeneration_save = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs) -> Pledge:
        # OrderedModel.save() auto-assigns order unless order_on_create is set
        if 'order' in kwargs:
            kwargs['order_on_create'] = kwargs.pop('order')
        return super()._create(model_class, *args, **kwargs)

    @post_generation
    @staticmethod
    def actions(obj: Pledge, create: bool, extracted: list[Action]) -> None:
        if create and extracted:
            for action in extracted:
                obj.actions.add(action)
            obj.save()
