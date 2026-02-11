from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastmcp.exceptions import ToolError

from mcp_server.__generated__.schema import (
    AddRelatedOrganizationInput,
    AttributeTypeFormat,
    AttributeTypeInput,
    CategoryInput,
    CategoryTypeInput,
    ChoiceOptionInput,
    MCPAddRelatedOrganization,
    MCPCreateAttributeType,
    MCPCreateCategory,
    MCPCreateCategoryType,
    MCPCreatePlan,
    MCPDeletePlan,
    MCPGetPlan,
    MCPListPlans,
    PlanFeaturesInput,
    PlanInput,
)

from .helpers import execute_operation

if TYPE_CHECKING:
    from fastmcp import FastMCP


async def list_plans() -> str:
    """
    List accessible plans.

    Returns a compact list of plans with identifier, name, and the owner organization and id.
    Use get_plan(identifier) for full details on a specific plan.
    """
    result = await execute_operation(MCPListPlans, MCPListPlans.Arguments())  # type: ignore[type-var]
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


async def get_plan(
    identifier: Annotated[str, "The unique identifier of the plan (e.g., 'sunnydale', 'tampere-ilmasto')"],
) -> MCPGetPlan:
    """Get detailed information about a specific action plan."""
    result = await execute_operation(MCPGetPlan, MCPGetPlan.Arguments(identifier=identifier))  # type: ignore[type-var]

    if result.plan is None:
        raise ToolError(f"Plan '{identifier}' not found")

    return result


async def create_plan(
    identifier: Annotated[str, 'Unique identifier for the plan (lowercase, dashes). Becomes part of the URL.'],
    name: Annotated[str, 'The official plan name in full form'],
    organization_id: Annotated[str, 'The ID (pk) of the owner organization'],
    primary_language: Annotated[str, "Primary language code (e.g. 'en', 'fi', 'de')"],
    short_name: Annotated[str | None, 'A shorter version of the plan name'] = None,
    other_languages: Annotated[list[str] | None, 'Additional language codes'] = None,
    theme_identifier: Annotated[str | None, 'Theme identifier for the plan UI'] = None,
    has_action_identifiers: Annotated[bool | None, 'Whether actions have meaningful identifiers'] = None,
    has_action_official_name: Annotated[bool | None, 'Whether to use the official name field'] = None,
    has_action_primary_orgs: Annotated[bool | None, 'Whether actions have a primary organization'] = None,
) -> MCPCreatePlan:
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
        MCPCreatePlan,
        MCPCreatePlan.Arguments(
            input=PlanInput(
                identifier=identifier,
                name=name,
                organizationId=organization_id,
                primaryLanguage=primary_language,
                shortName=short_name,
                otherLanguages=other_languages or [],
                themeIdentifier=theme_identifier,
                features=features,
            )
        ),
    )  # type: ignore[type-var]

    return result


async def create_category_type(
    plan_id: Annotated[str, 'The ID (pk) of the plan'],
    identifier: Annotated[str, 'Unique identifier for the category type'],
    name: Annotated[str, 'Display name of the category type'],
    usable_for_actions: Annotated[bool, 'Whether this category type can be used for actions'] = True,
    usable_for_indicators: Annotated[bool, 'Whether this category type can be used for indicators'] = False,
    select_widget: Annotated[str | None, "Selection widget: 'single' (default) or 'multiple'"] = None,
    hide_category_identifiers: Annotated[bool | None, "Set true if categories don't have meaningful identifiers"] = None,
    primary_action_classification: Annotated[
        bool,
        'Whether this category type is the primary action classification. '
        'NOTE: A Plan must have exactly one primary action classification.',
    ] = False,
) -> MCPCreateCategoryType:
    """
    Create a new category type for a plan.

    Category types group categories together (e.g. 'Theme', 'Sector', 'Strategy').
    A plan can have several category types.
    """
    result = await execute_operation(
        MCPCreateCategoryType,
        MCPCreateCategoryType.Arguments(
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
    )  # type: ignore[type-var]

    return result


async def create_category(
    type_id: Annotated[str, 'The ID (pk) of the category type this category belongs to'],
    identifier: Annotated[str, 'Unique identifier for the category within its type'],
    name: Annotated[str, 'Display name of the category'],
    parent_id: Annotated[str | None, 'ID of the parent category for nested hierarchies'] = None,
    order: Annotated[int | None, 'Sort order (0-based)'] = None,
) -> MCPCreateCategory:
    """
    Create a new category within a category type.

    Categories organize actions (e.g. themes, sectors). Use get_plan to find category type IDs.
    """
    result = await execute_operation(
        MCPCreateCategory,
        MCPCreateCategory.Arguments(
            input=CategoryInput(
                typeId=type_id,
                identifier=identifier,
                name=name,
                parentId=parent_id,
                order=order,
            )
        ),
    )  # type: ignore[type-var]

    return result


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
) -> MCPCreateAttributeType:
    """
    Create a new attribute type for actions in a plan.

    Attribute types define dynamic fields on actions (e.g. priority level, cost estimate).
    For choice-based formats, you must provide choice_options.
    """
    options: list[ChoiceOptionInput] | None = None
    if choice_options:
        options = [
            ChoiceOptionInput(identifier=str(opt['identifier']), name=str(opt['name']), order=int(opt['order']))
            for opt in choice_options
        ]

    result = await execute_operation(
        MCPCreateAttributeType,
        MCPCreateAttributeType.Arguments(
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
    )  # type: ignore[type-var]

    return result


async def delete_plan(
    id: Annotated[str, 'The ID (pk) or identifier of the plan to delete'],
) -> str:
    """
    Delete a recently created plan.

    Safety check: the plan must have been created within the last 2 days.
    This is intended for cleaning up test plans.
    """
    result = await execute_operation(
        MCPDeletePlan,
        MCPDeletePlan.Arguments(id=id),
    )  # type: ignore[type-var]

    if result.plan is None or not result.plan.delete_plan:
        raise ToolError(f"Failed to delete plan '{id}'")

    return f"Plan '{id}' deleted successfully."


async def add_related_organization(
    plan_id: Annotated[str, 'The ID (pk) or identifier of the plan to add the organization to'],
    organization_id: Annotated[str, 'The ID of the organization to add as a related organization'],
) -> MCPAddRelatedOrganization:
    """
    Add a related organization to a plan.

    This is useful for fixing orphaned organization hierarchies where child organizations are related to a plan but
    their parent is not.
    """
    result = await execute_operation(
        MCPAddRelatedOrganization,
        MCPAddRelatedOrganization.Arguments(input=AddRelatedOrganizationInput(planId=plan_id, organizationId=organization_id)),
    )  # type: ignore[type-var]

    if result.plan is None:
        raise ToolError('Failed to add related organization')

    return result


def register_plan_tools(mcp: FastMCP) -> None:
    """Register all plan-related MCP tools."""

    mcp.tool(list_plans)
    mcp.tool(get_plan)
    mcp.tool(create_plan)
    mcp.tool(delete_plan)
    mcp.tool(add_related_organization)
    mcp.tool(create_category_type)
    mcp.tool(create_category)
    mcp.tool(create_attribute_type)
