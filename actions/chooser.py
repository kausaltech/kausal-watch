from typing import Literal

from generic_chooser.views import ModelChooserViewSet, ModelChooserMixin
from generic_chooser.widgets import AdminChooser, LinkedFieldMixin
from django.utils.translation import gettext_lazy as _
from wagtail.search.backends import get_search_backend
from wagtail import hooks

from .models.action import Action
from .models.attributes import AttributeType
from .models.category import Category, CategoryLevel, CategoryType
from .models.plan import Plan
from aplans.types import WatchAdminRequest

from budget.models import DatasetSchema
from django.contrib.contenttypes.models import ContentType


class WatchModelChooserBase(ModelChooserMixin):
    def get_object_list(self, search_term=None, **kwargs):
        objs = self.get_unfiltered_object_list()

        if search_term:
            search_backend = get_search_backend()
            objs = search_backend.autocomplete(search_term, objs)

        return objs


class CategoryChooserMixin(WatchModelChooserBase):
    request: WatchAdminRequest

    def get_unfiltered_object_list(self):
        plan = self.request.user.get_active_admin_plan()
        objects = Category.objects.filter(type__plan=plan).distinct()
        return objects


class CategoryChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = CategoryChooserMixin

    icon = 'kausal-category'
    model = Category
    page_title = _("Choose a category")
    per_page = 30
    fields = ['identifier', 'name']


class CategoryChooser(AdminChooser):
    choose_one_text = _('Choose a category')
    choose_another_text = _('Choose another category')
    model = Category
    choose_modal_url_name = 'category_chooser:choose'


@hooks.register('register_admin_viewset')
def register_category_chooser_viewset():
    return CategoryChooserViewSet('category_chooser', url_prefix='category-chooser')


class CategoryTypeChooserMixin(WatchModelChooserBase):
    request: WatchAdminRequest

    def get_unfiltered_object_list(self):
        plan = self.request.get_active_admin_plan()
        return CategoryType.objects.filter(plan=plan)

    def user_can_create(self, user):
        # Don't let users create category types in the chooser
        return False


class CategoryTypeChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = CategoryTypeChooserMixin

    icon = 'kausal-category'
    model = CategoryType
    page_title = _("Choose a category type")
    per_page = 30
    fields = ['identifier', 'name']


class CategoryTypeChooser(AdminChooser):
    choose_one_text = _('Choose a category type')
    choose_another_text = _('Choose another category type')
    model = CategoryType
    choose_modal_url_name = 'category_type_chooser:choose'


@hooks.register('register_admin_viewset')
def register_category_type_chooser_viewset():
    return CategoryTypeChooserViewSet('category_type_chooser', url_prefix='category-type-chooser')


class CategoryLevelChooserMixin(ModelChooserMixin):
    request: WatchAdminRequest

    def get_unfiltered_object_list(self):
        plan = self.request.get_active_admin_plan()
        objects = CategoryLevel.objects.filter(type__plan=plan)
        type = self.request.GET.get('type')
        if type:
            objects = objects.filter(type=type)
        return objects

    def user_can_create(self, user):
        return False


class CategoryLevelChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = CategoryLevelChooserMixin

    icon = 'kausal-category'
    model = CategoryLevel
    page_title = _("Choose a category level")
    fields = ['order', 'name']


class CategoryLevelChooser(LinkedFieldMixin, AdminChooser):
    chooser_mixin_class = CategoryLevelChooserMixin
    model = CategoryLevel
    choose_modal_url_name = 'category_level_chooser:choose'


@hooks.register('register_admin_viewset')
def register_category_level_chooser_viewset():
    return CategoryLevelChooserViewSet('category_level_chooser', url_prefix='category-level-chooser')


class ActionChooserMixin(WatchModelChooserBase):
    request: WatchAdminRequest

    def get_unfiltered_object_list(self):
        plan = self.request.get_active_admin_plan()
        related_plans = Plan.objects.filter(pk=plan.pk) | plan.related_plans.all()
        objects = Action.objects.filter(plan__in=related_plans)
        return objects

    def get_row_data(self, item):
        return {
            'choose_url': self.get_chosen_url(item),
            'name': self.get_object_string(item),
            'plan': item.plan,
        }

    def get_results_template(self):
        return 'actions/chooser_results.html'

    def user_can_create(self, user):
        # Don't let users create actions in the chooser
        return False


class ActionChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = ActionChooserMixin

    icon = 'kausal-action'
    model = Action
    page_title = _("Choose an action")
    per_page = 30
    fields = ['identifier', 'name']


class ActionChooser(AdminChooser):
    choose_one_text = _('Choose an action')
    choose_another_text = _('Choose another action')
    model = Action
    choose_modal_url_name = 'action_chooser:choose'


@hooks.register('register_admin_viewset')
def register_action_chooser_viewset():
    return ActionChooserViewSet('action_chooser', url_prefix='action-chooser')


class PlanChooserMixin(WatchModelChooserBase):
    request: WatchAdminRequest

    def get_unfiltered_object_list(self):
        plan = self.request.get_active_admin_plan()
        return Plan.objects.filter(pk=plan.pk) | plan.related_plans.all()

    def get_row_data(self, item):
        return {
            'choose_url': self.get_chosen_url(item),
            'name': self.get_object_string(item),
        }

    def get_results_template(self):
        return 'actions/chooser_results.html'

    def user_can_create(self, user):
        # Don't let users create plans in the chooser
        return False


class PlanChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = PlanChooserMixin

    icon = 'kausal-plan'
    model = Plan
    page_title = _("Choose a plan")
    per_page = 30
    fields = ['identifier', 'name']


class PlanChooser(AdminChooser):
    choose_one_text = _('Choose a plan')
    choose_another_text = _('Choose another plan')
    model = Plan
    choose_modal_url_name = 'plan_chooser:choose'


@hooks.register('register_admin_viewset')
def register_plan_chooser_viewset():
    return PlanChooserViewSet('plan_chooser', url_prefix='plan-chooser')


class AttributeTypeChooserMixin(WatchModelChooserBase):
    request: WatchAdminRequest

    def get_unfiltered_object_list(self):
        scope = self.request.GET.get('scope', None)
        plan = self.request.get_active_admin_plan()
        cat_qs = AttributeType.objects.for_categories(plan)
        act_qs = AttributeType.objects.for_actions(plan)
        if scope:
            if scope == 'category':
                qs = cat_qs
            elif scope == 'action':
                qs = act_qs
            else:
                raise Exception("Unknown scope")
        else:
            qs = cat_qs | act_qs
        return qs.order_by('name')

    def user_can_create(self, user):
        return False


class AttributeTypeChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = AttributeTypeChooserMixin

    icon = 'kausal-attribute'
    model = AttributeType
    page_title = _("Choose a field")
    per_page = 30
    fields = ['name']


class AttributeTypeChooser(AdminChooser):
    choose_one_text = _('Choose a field')
    choose_another_text = _('Choose another field')
    model = AttributeType
    choose_modal_url_name = 'attribute_type_chooser:choose'
    scope: Literal['action', 'category'] | None

    def __init__(self, /, scope: Literal['action', 'category'] | None = None, **kwargs):
        self.scope = scope
        super().__init__(**kwargs)

    def get_choose_modal_url(self):
        ret = super().get_choose_modal_url()
        assert ret is not None
        if self.scope is not None:
            ret += '?scope=%s' % self.scope
        return ret


@hooks.register('register_admin_viewset')
def register_attribute_type_chooser_viewset():
    return AttributeTypeChooserViewSet('attribute_type_chooser', url_prefix='attribute-type-chooser')



class DatasetSchemaChooserMixin(WatchModelChooserBase):
    request: WatchAdminRequest

    def get_unfiltered_object_list(self):
        plan = self.request.get_active_admin_plan()
        scope = self.request.GET.get('scope')

        if scope == 'plan':
            content_type = ContentType.objects.get_for_model(Plan)
            return DatasetSchema.objects.filter(
                scopes__scope_content_type=content_type,
                scopes__scope_id=plan.id
            ).distinct()
        elif scope == 'categorytype':
            content_type = ContentType.objects.get_for_model(CategoryType)
            return DatasetSchema.objects.filter(
                scopes__scope_content_type=content_type,
                scopes__scope_id__in=plan.category_types.values_list('id', flat=True)
            ).distinct()
        else:
            return DatasetSchema.objects.none()

    def user_can_create(self, user):
        return False


class DatasetSchemaChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = DatasetSchemaChooserMixin
    icon = 'table'
    model = DatasetSchema
    page_title = _("Choose a dataset schema")
    per_page = 30
    fields = ['name', 'unit', 'time_resolution']

    def get_chooser_mixin_kwargs(self):
        kwargs = super().get_chooser_mixin_kwargs()
        kwargs['scope'] = self.request.GET.get('scope', 'plan')
        return kwargs

class DatasetSchemaChooser(AdminChooser):
    choose_one_text = _('Choose a dataset schema')
    choose_another_text = _('Choose another dataset schema')
    model = DatasetSchema
    choose_modal_url_name = 'dataset_schema_chooser:choose'

    def __init__(self, /, scope: Literal['plan', 'categorytype'] = 'plan', **kwargs):
        self.scope = scope
        super().__init__(**kwargs)

    def get_choose_modal_url(self):
        url = super().get_choose_modal_url()
        return f"{url}?scope={self.scope}"



@hooks.register('register_admin_viewset')
def register_dataset_schema_chooser_viewset():
    return DatasetSchemaChooserViewSet('dataset_schema_chooser', url_prefix='dataset-schema-chooser')
