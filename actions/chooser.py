from generic_chooser.views import ModelChooserViewSet, ModelChooserMixin
from generic_chooser.widgets import AdminChooser
from django.utils.translation import gettext_lazy as _
from wagtail.search.backends import get_search_backend
from wagtail.core import hooks

from .models import Action, Category, CategoryType, Plan


class CategoryChooserMixin(ModelChooserMixin):
    def get_unfiltered_object_list(self):
        plan = self.request.user.get_active_admin_plan()
        objects = Category.objects.filter(type__plan=plan).distinct()
        return objects

    def get_object_list(self, search_term=None, **kwargs):
        objs = self.get_unfiltered_object_list()

        if search_term:
            search_backend = get_search_backend()
            objs = search_backend.autocomplete(search_term, objs)

        return objs


class CategoryChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = CategoryChooserMixin

    icon = 'user'
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


class CategoryTypeChooserMixin(ModelChooserMixin):
    def get_unfiltered_object_list(self):
        plan = self.request.user.get_active_admin_plan()
        return CategoryType.objects.filter(plan=plan)

    def get_object_list(self, search_term=None, **kwargs):
        objs = self.get_unfiltered_object_list()

        if search_term:
            search_backend = get_search_backend()
            objs = search_backend.autocomplete(search_term, objs)

        return objs

    def user_can_create(self, user):
        # Don't let users create category types in the chooser
        return False


class CategoryTypeChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = CategoryTypeChooserMixin

    icon = 'folder-open-inverse'
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


class ActionChooserMixin(ModelChooserMixin):
    def get_unfiltered_object_list(self):
        plan = self.request.user.get_active_admin_plan()
        related_plans = Plan.objects.filter(pk=plan.pk) | plan.related_plans.all()
        objects = Action.objects.filter(plan__in=related_plans)
        return objects

    def get_object_list(self, search_term=None, **kwargs):
        objs = self.get_unfiltered_object_list()

        if search_term:
            search_backend = get_search_backend()
            objs = search_backend.autocomplete(search_term, objs)

        return objs

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

    icon = 'fa-cubes'
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
