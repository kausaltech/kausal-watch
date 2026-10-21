# Field Customizations

## Overview

A `BuiltInFieldCustomization` (`src/admin_site/models.py`) overrides one built-in model field for one
plan. Plan admins edit them under *Settings → Field customizations*. A customization has:

- a label and a help text override, for the admin form;
- *Visibility* (`instances_visible_for`) and *Edit rights* (`instances_editable_by`), the same access
  levels attribute types have (`InstancesVisibleForMixin` / `InstancesEditableByMixin` in
  `src/aplans/utils.py`).

Only registered fields can be chosen. The registry is in `src/admin_site/field_customization.py`.
Admin modules fill it with `register_customizable_fields()`: `Action` and `ActionTask` in
`src/actions/action_admin.py`, `Indicator` and `ActionIndicator` in `src/indicators/wagtail_admin.py`.
Fields under a `CustomizableBuiltInFieldPanel` are collected automatically. Relations edited in an
`InlinePanel` must be listed by hand, and for them only the access settings do anything.

## Where it is enforced

Unlike attribute types, a customization mostly affects **only the admin**. Check the table below
before assuming it hides anything from the public UI.

| Field | Admin | Public GraphQL / REST | Excel export |
|-------|-------|-----------------------|--------------|
| Plain fields (`Action.name`, `ActionTask.due_at`, ...) | Field removed or disabled (`BuiltInFieldCustomizationAwareEditHandlerMixin`) | Not enforced | Not enforced |
| `Action.tasks` | Tab dropped when not visible | Not enforced | Not enforced |
| `Action.contact_persons`, `Action.responsible_parties` | Tab gated; REST rejects edits when not editable | Not enforced | Not enforced |
| `ActionTask.responsible_parties`, `ActionTask.contact_persons` | Panel dropped, read-only, or editable (`ActionAdmin.get_task_panels`); REST ignores hidden and rejects non-editable edits | **Enforced** | **Enforced** |

The visibility of the action-level relations is deliberately not enforced publicly. Plans have set
those customizations expecting them to affect the admin only, and enforcing them would take data off
their sites. Enforcing them needs an audit of existing customizations first.

## Task assignees

The task assignees (`ActionTaskResponsibleParty`, `ActionTaskContactPerson`) are only shown if the
plan has `PlanFeatures.has_action_task_assignees`. That switch is superuser-only. Within such a plan,
the customization of each relation decides who sees it:

- **GraphQL** (`ActionTaskNode` in `src/actions/schema.py`) and **REST** (`ActionTaskSerializer` in
  `src/actions/api.py`) check `BuiltInFieldCustomization.is_field_visible_for()` with the task's
  action. The contact-person and moderator levels therefore refer to the contact persons of that
  action. Both load the plan's customizations once (`BuiltInFieldCustomization.for_plan()`, cached on
  `PlanSpecificCache` for GraphQL), not once per task.
- **REST writes** (the action table editor saves tasks with a bulk PUT of whole rows) follow the admin
  form: a relation hidden from the user is ignored, as is any value equal to what is stored, and
  changing a relation the user may not edit (`BuiltInFieldCustomization.is_field_editable_by()`) is
  rejected with a 400. The grid does not lock such columns; the error shows on the cell.
- **Excel export** (`ExcelReport.task_assignments_visible`) has no per-cell filtering. Like attribute
  types (`reports.utils.is_visible_in_full_export`), it includes the action-dependent levels only for
  plan admins.
- **Contact persons** must also pass the plan's `contact_persons_public_data` setting
  (`ActionTask.get_redacted_contact_persons()`), so the stricter of the two settings wins. In REST,
  someone who may modify the task's action (`User.can_modify_action()`) is exempt from that setting,
  as in the admin form: the table editor writes back what it read, so a redacted list would delete
  the assignments it left out.
- **Admin:** the assignee panel headings carry the "public / non-public field" marker, derived from
  the same settings, when the plan has `display_field_visibility_restrictions`.
