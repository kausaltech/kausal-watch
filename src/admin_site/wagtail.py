from __future__ import annotations

from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, cast

import reversion
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from django.forms.models import ModelForm
from django.urls.base import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from modeltrans.translator import get_i18n_field
from reversion.revisions import add_to_revision, create_revision, set_comment, set_user
from wagtail.admin.forms.models import WagtailAdminModelForm, registry as form_field_overrides
from wagtail.admin.panels import (
    InlinePanel,
    MultiFieldPanel,
    ObjectList,
    TabbedInterface,
)
from wagtail.admin.panels.field_panel import FieldPanel
from wagtail.admin.widgets.button import ListingButton

from kausal_common.i18n.helpers import convert_language_code, get_language_from_default_language_field
from kausal_common.users import user_or_bust

from aplans.context_vars import ctx_instance, ctx_request
from aplans.utils import InstancesVisibleForMixin, PlanRelatedModel

from .utils import FieldLabelRenderer, admin_req

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from django.forms.models import ModelChoiceField
    from django.http import HttpRequest
    from django_stubs_ext import StrOrPromise
    from modeltrans.fields import TranslatedVirtualField
    from wagtail.admin.panels.base import Panel

    from kausal_common.datasets.models import DatasetScopeType

    from aplans.cache import PlanSpecificCache
    from aplans.types import WatchAdminRequest

    from actions.models import AttributeType
    from actions.models.category import CommonCategoryType
    from actions.models.plan import Plan
    from users.models import User


class TranslationsPanel(MultiFieldPanel[Any]):
    """
    The per-language inputs of one translatable field, in a section below the field that can be folded away.

    Rendered as a native `<details>` element rather than a Wagtail collapsible panel, because Wagtail only makes
    top-level panels collapsible and translations also appear inside groups and inline rows. The section starts
    open when any translation is empty or has an error, so missing translations are not tucked out of sight.
    """

    class BoundPanel(MultiFieldPanel.BoundPanel):
        template_name = 'admin_site/panels/translations_panel.html'

        if TYPE_CHECKING:
            # Inherited from PanelGroup.BoundPanel at runtime; the Wagtail stubs leave it off MultiFieldPanel.BoundPanel.
            visible_children: list[Panel.BoundPanel[Any, Any, Any]]

        @cached_property
        def is_open(self) -> bool:
            for child in self.visible_children:
                field_name = getattr(child.panel, 'field_name', None)
                if field_name is None or field_name not in self.form.fields:
                    continue
                bound_field = self.form[field_name]
                if bound_field.errors:
                    return True
                value = bound_field.value()
                if value is None or (isinstance(value, str) and not value.strip()):
                    return True
            return False


def insert_model_translation_panels[M: Model, PanelT: Panel[Any]](
    model: type[M],
    panels: Sequence[PanelT],
    request: HttpRequest,
    instance: Plan | AttributeType | None = None,
) -> list[PanelT | TranslationsPanel]:
    """
    Return `panels` with a `TranslationsPanel` after each field that has translations.

    The section holds one input per other language of `instance`, labelled with the language's name.
    """
    i18n_field = get_i18n_field(model)
    if not i18n_field:
        return list(panels)

    out: list[PanelT | TranslationsPanel] = []
    if instance is None:
        user = user_or_bust(request.user)
        instance = user.get_active_admin_plan()

    language_names = {code.lower(): str(name) for code, name in settings.LANGUAGES}
    field_map: dict[str, dict[str | None, TranslatedVirtualField]] = {}
    for f in i18n_field.get_translated_fields():
        field_map.setdefault(f.original_name, {})[f.language] = f

    for p in panels:
        out.append(p)
        if not isinstance(p, FieldPanel):
            continue
        t_fields = field_map.get(p.field_name)
        if not t_fields:
            continue

        # Translations are modeltrans virtual fields, which Wagtail doesn't give its widgets (e.g. the auto-height
        # textarea), so use the widget the original field gets.
        original_field = model._meta.get_field(p.field_name)
        widget = p.widget or (form_field_overrides.get(original_field) or {}).get('widget')
        # The visible label is just the language; screen readers also hear which field is being translated.
        field_label = p.heading or capfirst(getattr(original_field, 'verbose_name', p.field_name))
        language_panels: list[Panel[Any]] = []
        for lang_code in instance.other_languages:
            django_code = convert_language_code(lang_code, 'django')
            tf = t_fields.get(django_code)
            if not tf:
                continue
            language_name = language_names.get(django_code.lower(), lang_code)
            heading = format_html('<span class="w-sr-only">{}: </span>{}', field_label, language_name)
            language_panels.append(type(p)(tf.name, heading=heading, widget=widget))
        if language_panels:
            out.append(TranslationsPanel(language_panels))
    return out


def get_translation_tabs(
    instance: Model, request: HttpRequest | None, include_all_languages: bool = False, extra_panels=None
) -> list[Panel[Any]]:
    """
    Get tabs for entering translated strings.

    If `include_all_languages` is true, a tab is shown for each language that is not the default for the given instance.
    This default language is determined by the `default_language` argument of the model's i18n field. If there is no
    such argument, the global default language from `settings.LANGUAGE_CODE` is used.
    If `include_all_languages` is false, a tab is shown for each language supported by the currently active plan except,
    just like before, the default language of the instance. Only then is `request` needed.
    `extra_panels` maps a language code to a list of panels that should be put on the tab of that language.
    """
    if extra_panels is None:
        extra_panels = {}

    model = type(instance)
    i18n_field = get_i18n_field(model)
    if not i18n_field:
        return []
    tabs: list[Panel[Any]] = []

    languages_by_code = {x[0].lower(): x[1] for x in settings.LANGUAGES}
    if include_all_languages:
        languages = list(languages_by_code.keys())
    else:
        assert request is not None
        plan = user_or_bust(request.user).get_active_admin_plan()
        languages = [plan.primary_language_lowercase] + [lang.lower() for lang in plan.other_languages]

    # Omit default language because it's stored in the model field without a modeltrans language suffix
    default_language = get_language_from_default_language_field(instance, i18n_field)
    languages = [lang for lang in languages if lang != default_language]

    for lang_code in languages:
        assert lang_code == lang_code.lower()
        panels = []
        for field in i18n_field.get_translated_fields():
            if field.language != lang_code:
                continue
            panels.append(FieldPanel(field.name))
        panels += extra_panels.get(lang_code, [])
        tabs.append(ObjectList(panels, heading=languages_by_code[lang_code]))
    return tabs


def get_default_language_tab_heading(instance: Model, heading: StrOrPromise) -> str:
    """
    Label a tab holding an instance's untranslated fields with the language they are in.

    `get_translation_tabs()` leaves out the instance's default language because its values live in the untranslated
    fields. Without the language in the heading of the tab holding those fields, users cannot tell which language to
    enter there and look in vain for a tab of the default language.
    """
    language = get_language_from_default_language_field(instance)
    languages_by_code = {code.lower(): name for code, name in settings.LANGUAGES}
    return _('%(heading)s (%(language)s)') % {'heading': heading, 'language': languages_by_code[language]}


class AdminOnlyPanel(ObjectList):
    pass


class AplansAdminModelForm[M: Model](WagtailAdminModelForm[M, 'User']):
    plan: Plan


if TYPE_CHECKING:
    BoundFieldPanelMixinBase = FieldPanel.BoundPanel
else:
    BoundFieldPanelMixinBase = object


class BoundPlanFilteredFieldPanelMixin(BoundFieldPanelMixinBase):
    """Mixin for bound panels to filter the related model queryset based on the active plan."""

    request: WatchAdminRequest

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.bound_field is None:
            # Bound without a form, as when comparing revisions
            return
        field = cast('ModelChoiceField[Any]', self.bound_field.field)
        queryset = field.queryset
        assert queryset is not None
        plan = self.request.get_active_admin_plan()
        related_model = queryset.model
        assert issubclass(related_model, PlanRelatedModel)
        field.queryset = related_model.filter_by_plan(plan, queryset)


class PlanFilteredFieldPanel[M: Model](FieldPanel[M]):
    class BoundPanel(BoundPlanFilteredFieldPanelMixin, FieldPanel.BoundPanel):
        pass


class BoundCustomizableBuiltInFieldPanelMixin(BoundFieldPanelMixinBase):
    """Mixin for bound panels for built-in fields to enable customizations by BuiltInFieldCustomization."""

    request: WatchAdminRequest

    def __init__(self, **kwargs):
        from admin_site.models import BuiltInFieldCustomization

        super().__init__(**kwargs)
        plan = self.request.get_active_admin_plan()
        is_public_field = True
        try:
            customization: BuiltInFieldCustomization = BuiltInFieldCustomization.objects.get(
                plan=plan,
                content_type=ContentType.objects.get_for_model(self.panel.model),
                field_name=self.field_name,
            )
        except BuiltInFieldCustomization.DoesNotExist:
            pass
        else:
            if customization.help_text_override:
                self.help_text = customization.help_text_override
            if customization.label_override:
                self.heading = customization.label_override
            if customization.instances_visible_for != InstancesVisibleForMixin.VisibleFor.PUBLIC:
                is_public_field = False
        self.heading = FieldLabelRenderer(plan)(self.heading, public=is_public_field)


class CustomizableBuiltInFieldPanel[M: Model](FieldPanel[M]):
    class BoundPanel(BoundCustomizableBuiltInFieldPanelMixin, FieldPanel.BoundPanel):
        pass


class CustomizableBuiltInPlanFilteredFieldPanel[M: Model](FieldPanel[M]):  # Ugh...
    class BoundPanel(BoundCustomizableBuiltInFieldPanelMixin, BoundPlanFilteredFieldPanelMixin, FieldPanel.BoundPanel):
        pass


if TYPE_CHECKING:

    class FieldPanelMixinBase[M: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]](FieldPanel[M, Any, FormT]):
        pass

    class TabbedInterfaceMixinBase[M: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]](TabbedInterface[M, FormT]):
        pass

else:

    class FieldPanelMixinBase[M: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]]:
        pass

    class TabbedInterfaceMixinBase[M: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]]:
        pass


def _translated_field_names_by_original(model: type[Model]) -> dict[str, list[str]]:
    """Map each translated field of `model` to the modeltrans field names that carry its languages."""
    i18n_field = get_i18n_field(model)
    if i18n_field is None:
        return {}
    names_by_original: dict[str, list[str]] = {}
    for field in i18n_field.get_translated_fields():
        names_by_original.setdefault(field.original_name, []).append(field.name)
    return names_by_original


class BuiltInFieldCustomizationAwareEditHandlerMixin[M: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]](
    TabbedInterfaceMixinBase[M, FormT]
):
    """
    Mixin to make an edit handler take instances of BuiltInFieldCustomization into account.

    It will delete all fields from the edit handler's form that are not visible to the current user.
    """

    BoundPanel: Any

    def get_form_class(self):
        from admin_site.models import BuiltInFieldCustomization

        form_class = super().get_form_class()
        request = ctx_request.get()
        instance = ctx_instance.get()
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()

        def change_base_fields(form_class: type[WagtailAdminModelForm], model: type[Model]) -> None:
            customizations_qs = BuiltInFieldCustomization.objects.filter(
                plan=plan,
                content_type=ContentType.objects.get_for_model(model),
            )
            # A customization names the untranslated field, but modeltrans gives a translated field
            # one form field per language, and the translation tabs render those with plain panels
            # of their own. Without applying the customization to them as well, restricting
            # `description` would still leave `description_fi` on the Finnish tab for everyone.
            translated_names = _translated_field_names_by_original(model)
            customizations: dict[str, BuiltInFieldCustomization] = {}
            for customization in customizations_qs:
                customizations[customization.field_name] = customization
                for translated_name in translated_names.get(customization.field_name, ()):
                    customizations[translated_name] = customization
            for field_name in list(form_class.base_fields.keys()):
                customization = customizations.get(field_name)
                if customization:
                    if not customization.is_instance_visible_for(user, plan, instance):
                        del form_class.base_fields[field_name]
                        continue
                    if not customization.is_instance_editable_by(user, plan, instance):
                        form_class.base_fields[field_name].disabled = True
                        form_class.base_fields[field_name].required = False

        assert self.model is not None
        # Disable / remove built-in fields that are not editable / visible due to customization
        change_base_fields(form_class, self.model)
        for formset in form_class.formsets.values():
            assert formset.model is not None
            change_base_fields(formset.form, formset.model)

        return form_class


def get_dataset_listing_buttons(request: HttpRequest, obj: DatasetScopeType) -> list[ListingButton]:
    """Return the buttons that add or edit the datasets of `obj`, for a snippet listing."""
    if find_spec('kausal_watch_extensions') is None:
        return []
    from kausal_watch_extensions.dataset_editor import DatasetViewSet  # type: ignore[import-not-found]

    cache: PlanSpecificCache = getattr(request, 'admin_cache')  # noqa: B009
    buttons: list[ListingButton] = []
    for schema, matching_dataset in cache.get_dataset_schemas_for_object(obj):
        if matching_dataset:
            url = reverse(DatasetViewSet().get_url_name('edit'), args=[matching_dataset.pk])
            label = _('Edit %(schema_name)s') % {'schema_name': schema.name}
            icon_name = 'edit'
        else:
            url = reverse(DatasetViewSet().get_url_name('add'))
            url += f'?dataset_schema_uuid={schema.uuid}&model={obj._meta.label}&object_id={obj.pk}'
            label = _('Add %(schema_name)s') % {'schema_name': schema.name}
            icon_name = 'plus'
        buttons.append(ListingButton(label, url=url, icon_name=icon_name))
    return buttons


class AplansTabbedInterface[M: Model, F: ModelForm[Any] = ModelForm[Any]](TabbedInterface[M, F]):
    class BoundPanel(TabbedInterface.BoundPanel[Any, Any, Any]):
        pass

    def get_bound_panel(
        self,
        instance: M | None = None,
        request: HttpRequest | None = None,
        form=None,
        prefix='panel',
    ):
        if request is not None:
            req = admin_req(request)
            plan = req.get_active_admin_plan()
            user = req.user
            is_admin = user.is_general_admin_for_plan(plan)
        else:
            is_admin = False
        if not is_admin:
            for child in list(self.children):
                if isinstance(child, AdminOnlyPanel):
                    cast('list[Panel[Any]]', self.children).remove(child)

        return super().get_bound_panel(instance, request, form, prefix)


def execute_admin_post_save_tasks(instance: Model, user: User):
    handle_admin_save = getattr(instance, 'handle_admin_save', None)
    if handle_admin_save:
        handle_admin_save(
            context={
                'user': user,
                'operation': 'edit',
            },
        )
    success_message = _("%(model_name)s '%(object)s' updated.") % {
        'model_name': capfirst(instance._meta.verbose_name),
        'object': instance,
    }
    if not reversion.is_registered(instance):
        return
    with create_revision():
        set_comment(success_message)
        add_to_revision(instance)
        set_user(user)


class CondensedInlinePanel[M: Model, RelatedM: Model](InlinePanel[M, RelatedM]):
    pass


_hidden_panel_classes: dict[type[Any], type[Any]] = {}


def _hidden_panel_class(panel_cls: type[Any]) -> type[Any]:
    """Return (and cache) a subclass of `panel_cls` whose bound panel is never shown."""
    hidden_cls = _hidden_panel_classes.get(panel_cls)
    if hidden_cls is not None:
        return hidden_cls

    def is_shown(self) -> bool:
        return False

    bound_panel_cls = type('BoundPanel', (panel_cls.BoundPanel,), {'is_shown': is_shown})
    hidden_cls = type(f'Hidden{panel_cls.__name__}', (panel_cls,), {'BoundPanel': bound_panel_cls})
    _hidden_panel_classes[panel_cls] = hidden_cls
    return hidden_cls


def gate_panel_visibility[P: Panel](panel_cls: type[P], *, is_visible: bool) -> type[P]:
    """
    Return `panel_cls` if the panel should be visible, otherwise a subclass that is never shown.

    Use this to hide a panel whose visibility is restricted, e.g. by a `BuiltInFieldCustomization`.
    Note that hiding a panel this way keeps its fields and formsets in the form; remove the panel
    from the edit handler altogether if the data must not be editable either.
    """
    if is_visible:
        return panel_cls
    return cast('type[P]', _hidden_panel_class(panel_cls))


def diff_common_category_types(
    old_ccts: Iterable[CommonCategoryType], new_ccts: Iterable[CommonCategoryType]
) -> tuple[list[CommonCategoryType], list[CommonCategoryType]]:
    """
    Return the common category types that were added and removed.

    Compares by primary key in Python instead of using `QuerySet.difference()`,
    because an empty operand (`pk__in=[]`) makes Django emit an `EXCEPT` with a
    nested `ORDER BY`, which PostgreSQL rejects.
    """
    old_by_pk = {cct.pk: cct for cct in old_ccts}
    new_by_pk = {cct.pk: cct for cct in new_ccts}
    added = [cct for pk, cct in new_by_pk.items() if pk not in old_by_pk]
    removed = [cct for pk, cct in old_by_pk.items() if pk not in new_by_pk]
    return added, removed
