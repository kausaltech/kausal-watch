from generic_chooser.views import ModelChooserViewSet, ModelChooserMixin, ModelChooserCreateTabMixin
from generic_chooser.widgets import AdminChooser
from django.utils.translation import gettext_lazy as _
from django.forms.models import modelform_factory
from wagtailautocomplete.widgets import Autocomplete as AutocompleteWidget
from wagtail.search.backends import get_search_backend
from wagtail.core import hooks
from dal import autocomplete
from .models import Person


class PersonChooserMixin(ModelChooserMixin):
    def get_unfiltered_object_list(self):
        objects = self.model.objects.all()
        if self.order_by:
            objects = objects.order_by('last_name', 'first_name')
        return objects

    def get_object_list(self, search_term=None, **kwargs):
        plan = self.request.user.get_active_admin_plan()
        object_list = self.get_unfiltered_object_list().available_for_plan(plan)

        if search_term:
            search_backend = get_search_backend()
            object_list = search_backend.autocomplete(search_term, object_list)

        return object_list

    def get_row_data(self, item):
        avatar_url = item.get_avatar_url(self.request, '50x50')
        return {
            'choose_url': self.get_chosen_url(item),
            'name': self.get_object_string(item),
            'title': item.title,
            'organization': item.organization_new,
            'avatar_url': avatar_url,
        }

    def get_results_template(self):
        return 'people/chooser_results.html'


class PersonModelChooserCreateTabMixin(ModelChooserCreateTabMixin):
    create_tab_label = _("Create new")

    def get_initial(self):
        plan = self.request.user.get_active_admin_plan()
        return {'organization': plan.organization_new}

    def get_form_class(self):
        if self.form_class:
            return self.form_class

        organization_widget = autocomplete.ModelSelect2(url='organization-autocomplete')

        self.form_class = modelform_factory(self.model, fields=self.fields, widgets=dict(
            organization=organization_widget
        ))
        return self.form_class


class PersonChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = PersonChooserMixin
    create_tab_mixin_class = PersonModelChooserCreateTabMixin

    icon = 'user'
    model = Person
    page_title = _("Choose person")
    per_page = 10
    order_by = ('last_name', 'first_name')
    fields = ['first_name', 'last_name', 'email', 'title', 'organization']


class PersonChooser(AdminChooser):
    choose_one_text = _('Choose a person')
    choose_another_text = _('Choose another person')
    link_to_chosen_text = _('Edit this person')
    model = Person
    choose_modal_url_name = 'person_chooser:choose'


@hooks.register('register_admin_viewset')
def register_person_chooser_viewset():
    return PersonChooserViewSet('person_chooser', url_prefix='person-chooser')
