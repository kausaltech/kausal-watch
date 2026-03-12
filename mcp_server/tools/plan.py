from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from fastmcp import Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from mcp_server.__generated__.schema import (
    AddRelatedOrganization,
    AddRelatedOrganizationInput,
    AttributeTypeDetails,
    AttributeTypeFormat,
    AttributeTypeInput,
    CategoryDetails,
    CategoryInput,
    CategoryTypeDetails,
    CategoryTypeInput,
    CategoryTypeSelectWidget,
    ChoiceOptionInput,
    CreateAttributeType,
    CreateCategory,
    CreateCategoryType,
    CreatePlan,
    DeletePlan,
    GetPlan,
    ListPlans,
    PlanConcise,
    PlanDetails,
    PlanFeaturesInput,
    PlanInput,
)

from .helpers import (
    WRITE_AUTH_DURATION_CHOICES,
    authorize_mcp_plan_write_access,
    check_operation_result,
    execute_operation,
    require_mcp_plan_write_authorization,
    resolve_plan_by_id_or_identifier,
    resolve_plan_ref_from_category_type,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

from .helpers import register_tool


@register_tool(annotations=ToolAnnotations(title='List plans', readOnlyHint=True, openWorldHint=False))
async def list_plans() -> str:
    """
    List accessible plans.

    Returns a compact list of plans with identifier, name, and the owner organization and id.
    Use get_plan(identifier) for full details on a specific plan.
    """
    result = await execute_operation(ListPlans, ListPlans.Arguments())
    if result.plans is None:
        raise ToolError('No plans found')

    lines: list[str] = []
    for plan in result.plans:
        name = plan.name
        if plan.short_name and plan.short_name != plan.name:
            name = f'{plan.name} ({plan.short_name})'
        if plan.version_name:
            name = f'{name} [{plan.version_name}]'
        owner_org = plan.organization
        lines.append(f'{plan.identifier}: {name} <{owner_org.name} [{owner_org.id}]>')

    return '\n'.join(lines)


@register_tool(annotations=ToolAnnotations(title='Get detailed information about a plan', readOnlyHint=True, openWorldHint=False))
async def get_plan(
    identifier: Annotated[str, "The unique identifier of the plan (e.g., 'sunnydale', 'tampere-ilmasto')"],
) -> PlanDetails:
    """Get detailed information about a specific action plan."""
    result = await execute_operation(GetPlan, GetPlan.Arguments(identifier=identifier))

    if result.plan is None:
        msg = f"Plan '{identifier}' not found"
        raise ToolError(msg)

    return result.plan


@register_tool(annotations=ToolAnnotations(title='Create a new action plan'))
async def create_plan(  # noqa: PLR0913
    identifier: Annotated[str, 'Unique identifier for the plan (lowercase, dashes). Becomes part of the URL.'],
    name: Annotated[str, 'The official plan name in full form'],
    organization_id: Annotated[str, 'The ID (pk) of the owner organization'],
    primary_language: Annotated[str, "Primary language code (e.g. 'en', 'fi', 'de')"],
    country: Annotated[str, "ISO 3166-1 country code (e.g. 'FI', 'DE', 'US')"],
    short_name: Annotated[str | None, 'A shorter version of the plan name'] = None,
    other_languages: Annotated[list[str] | None, 'Additional language codes'] = None,
    theme_identifier: Annotated[str | None, 'Theme identifier for the plan UI'] = None,
    has_action_identifiers: Annotated[bool | None, 'Whether actions have meaningful identifiers'] = None,
    has_action_official_name: Annotated[bool | None, 'Whether to use the official name field'] = None,
    has_action_primary_orgs: Annotated[bool | None, 'Whether actions have a primary organization'] = None,
) -> PlanDetails:
    """
    Create a new action plan.

    Requires superuser access. Use list_organizations to find the owner organization ID.
    """
    features: PlanFeaturesInput | None = None
    feature_flags = (has_action_identifiers, has_action_official_name, has_action_primary_orgs)
    if any(v is not None for v in feature_flags):
        features = PlanFeaturesInput(
            hasActionIdentifiers=has_action_identifiers,
            hasActionOfficialName=has_action_official_name,
            hasActionPrimaryOrgs=has_action_primary_orgs,
        )

    result = await execute_operation(
        CreatePlan,
        CreatePlan.Arguments(
            input=PlanInput(
                identifier=identifier,
                name=name,
                organizationId=organization_id,
                primaryLanguage=primary_language,
                shortName=short_name,
                otherLanguages=other_languages or [],
                themeIdentifier=theme_identifier,
                features=features,
                country=country,
            )
        ),
    )

    return check_operation_result(result.plan.create_plan)


@register_tool
async def create_category_type(
    plan_id: Annotated[str, 'The ID (pk) of the plan'],
    identifier: Annotated[str, 'Unique identifier for the category type'],
    name: Annotated[str, 'Display name of the category type'],
    usable_for_actions: Annotated[bool, 'Whether this category type can be used for actions'] = True,
    usable_for_indicators: Annotated[bool, 'Whether this category type can be used for indicators'] = False,
    select_widget: Annotated[
        CategoryTypeSelectWidget | None, 'Can multiple categories of this type apply to a single target or just one?'
    ] = None,
    hide_category_identifiers: Annotated[bool | None, "Set true if categories don't have meaningful identifiers"] = None,
    primary_action_classification: Annotated[
        bool,
        'Whether this category type is the primary action classification. '
        'NOTE: A Plan must have exactly one primary action classification.',
    ] = False,
    ctx: Context | None = None,
) -> CategoryTypeDetails:
    """
    Create a new category type for a plan.

    Category types group categories together (e.g. 'Theme', 'Sector', 'Strategy').
    A plan can have several category types.
    """
    if ctx is None:
        raise ToolError('Context is required for write authorization.')
    await require_mcp_plan_write_authorization(plan_ref=plan_id, tool_name='create_category_type', ctx=ctx)

    result = await execute_operation(
        CreateCategoryType,
        CreateCategoryType.Arguments(
            input=CategoryTypeInput(
                planId=plan_id,
                identifier=identifier,
                name=name,
                usableForActions=usable_for_actions,
                usableForIndicators=usable_for_indicators,
                selectWidget=select_widget,
                hideCategoryIdentifiers=hide_category_identifiers,
                primaryActionClassification=primary_action_classification,
            )
        ),
    )

    return check_operation_result(result.plan.create_category_type)


@register_tool
async def create_category(
    type_id: Annotated[str, 'The ID (pk) of the category type this category belongs to'],
    identifier: Annotated[str, 'Unique identifier for the category within its type'],
    name: Annotated[str, 'Display name of the category'],
    parent_id: Annotated[str | None, 'ID of the parent category for nested hierarchies'] = None,
    order: Annotated[int | None, 'Sort order (0-based)'] = None,
    ctx: Context | None = None,
) -> CategoryDetails:
    """
    Create a new category within a category type.

    Categories organize actions (e.g. themes, sectors). Use get_plan to find category type IDs.
    """
    if ctx is None:
        raise ToolError('Context is required for write authorization.')
    plan_ref = await resolve_plan_ref_from_category_type(type_id)
    await require_mcp_plan_write_authorization(plan_ref=plan_ref, tool_name='create_category', ctx=ctx)

    result = await execute_operation(
        CreateCategory,
        CreateCategory.Arguments(
            input=CategoryInput(
                typeId=type_id,
                identifier=identifier,
                name=name,
                parentId=parent_id,
                order=order,
            )
        ),
    )

    return check_operation_result(result.plan.create_category)


@register_tool
async def create_attribute_type(
    plan_id: Annotated[str, 'The ID (pk) of the plan'],
    identifier: Annotated[str, 'Unique identifier for the attribute type'],
    name: Annotated[str, 'Display name of the attribute type'],
    format: Annotated[
        AttributeTypeFormat,
        'Attribute format: ORDERED_CHOICE, UNORDERED_CHOICE, OPTIONAL_CHOICE_WITH_TEXT,'
        ' TEXT, RICH_TEXT, NUMERIC, or CATEGORY_CHOICE',
    ],
    help_text: Annotated[str | None, 'Help text shown to users editing this attribute'] = None,
    unit_id: Annotated[str | None, 'ID of the unit (for NUMERIC attributes)'] = None,
    choice_options: Annotated[
        list[dict[str, str | int]] | None,
        "List of choice options, each with 'identifier' (str), 'name' (str),"
        " and 'order' (int). Required for choice-type formats.",
    ] = None,
    ctx: Context | None = None,
) -> AttributeTypeDetails:
    """
    Create a new attribute type for actions in a plan.

    Attribute types define dynamic fields on actions (e.g. priority level, cost estimate).
    For choice-based formats, you must provide choice_options.
    """
    if ctx is None:
        raise ToolError('Context is required for write authorization.')
    await require_mcp_plan_write_authorization(plan_ref=plan_id, tool_name='create_attribute_type', ctx=ctx)

    options: list[ChoiceOptionInput] | None = None
    if choice_options:
        options = [
            ChoiceOptionInput(identifier=str(opt['identifier']), name=str(opt['name']), order=int(opt['order']))
            for opt in choice_options
        ]

    result = await execute_operation(
        CreateAttributeType,
        CreateAttributeType.Arguments(
            input=AttributeTypeInput(
                planId=plan_id,
                identifier=identifier,
                name=name,
                format=format,
                helpText=help_text,
                unitId=unit_id,
                choiceOptions=options,
            )
        ),
    )

    return check_operation_result(result.plan.create_attribute_type)


@register_tool(annotations=ToolAnnotations(destructiveHint=True, title='Delete an action plan'))
async def delete_plan(
    id: Annotated[str, 'The ID (pk) or identifier of the plan to delete'],
    ctx: Context | None = None,
) -> str:
    """
    Delete a recently created plan.

    Safety check: the plan must have been created within the last 2 days.
    This is intended for cleaning up test plans.
    """
    if ctx is None:
        raise ToolError('Context is required for write authorization.')
    await require_mcp_plan_write_authorization(plan_ref=id, tool_name='delete_plan', ctx=ctx)

    result = await execute_operation(
        DeletePlan,
        DeletePlan.Arguments(id=id),
    )

    check_operation_result(result.plan.delete_plan)
    return f"Plan '{id}' deleted successfully."


@register_tool(annotations=ToolAnnotations(title='Add a related organization to a plan'))
async def add_related_organization(
    plan_id: Annotated[str, 'The ID (pk) or identifier of the plan to add the organization to'],
    organization_id: Annotated[str, 'The ID of the organization to add as a related organization'],
    ctx: Context | None = None,
) -> PlanConcise:
    """
    Add a related organization to a plan.

    This is useful for fixing orphaned organization hierarchies where child organizations are related to a plan but
    their parent is not.
    """
    if ctx is None:
        raise ToolError('Context is required for write authorization.')
    await require_mcp_plan_write_authorization(plan_ref=plan_id, tool_name='add_related_organization', ctx=ctx)

    result = await execute_operation(
        AddRelatedOrganization,
        AddRelatedOrganization.Arguments(input=AddRelatedOrganizationInput(planId=plan_id, organizationId=organization_id)),
    )

    return check_operation_result(result.plan.add_related_organization)


@register_tool(annotations=ToolAnnotations(title='Authorize plan edits for MCP tools', idempotentHint=True))
async def authorize_plan_edits(
    plan_id: Annotated[str, 'The ID (pk) or identifier of the plan to authorize'],
    duration: Annotated[
        Literal['15m', '1h', '8h', '24h'],
        "Authorization duration. Allowed values: '15m', '1h', '8h', '24h'.",
    ],
) -> str:
    """
    Authorize MCP write operations for a plan for a limited time.

    This tool is useful for pre-authorizing a set of write operations before issuing mutations.
    """
    if duration not in WRITE_AUTH_DURATION_CHOICES:
        raise ToolError(f'Invalid duration: {duration}')
    plan = await resolve_plan_by_id_or_identifier(plan_id)
    return await authorize_mcp_plan_write_access(
        plan_ref=str(plan.id),
        duration_key=duration,
        granted_by_tool='authorize_plan_edits',
    )


def register_plan_tools(_mcp: FastMCP) -> None:
    """Register all plan-related MCP tools."""
    pass
