from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from mcp_server.generated_base import ArgumentsModel, InputTypeModel, OperationModel


class ActionContactPersonRole(str, Enum):
    """An enumeration."""

    EDITOR = 'EDITOR'
    'Editor'
    MODERATOR = 'MODERATOR'
    'Moderator'


class ActionDateFormat(str, Enum):
    """An enumeration."""

    FULL = 'FULL'
    'Day, month and year (31.12.2020)'
    MONTH_YEAR = 'MONTH_YEAR'
    'Month and year (12.2020)'
    YEAR = 'YEAR'
    'Year (2020)'


class ActionIndicatorEffectType(str, Enum):
    """An enumeration."""

    INCREASES = 'INCREASES'
    'increases'
    DECREASES = 'DECREASES'
    'decreases'


class ActionResponsiblePartyRole(str, Enum):
    """An enumeration."""

    NONE = 'NONE'
    'Unspecified'
    PRIMARY = 'PRIMARY'
    'Primary responsible party'
    COLLABORATOR = 'COLLABORATOR'
    'Collaborator'


class ActionStatusSummaryIdentifier(str, Enum):
    """An enumeration."""

    COMPLETED = 'COMPLETED'
    ON_TIME = 'ON_TIME'
    IN_PROGRESS = 'IN_PROGRESS'
    NOT_STARTED = 'NOT_STARTED'
    LATE = 'LATE'
    CANCELLED = 'CANCELLED'
    OUT_OF_SCOPE = 'OUT_OF_SCOPE'
    MERGED = 'MERGED'
    POSTPONED = 'POSTPONED'
    UNDEFINED = 'UNDEFINED'


class ActionTaskState(str, Enum):
    """An enumeration."""

    NOT_STARTED = 'NOT_STARTED'
    'not started'
    IN_PROGRESS = 'IN_PROGRESS'
    'in progress'
    COMPLETED = 'COMPLETED'
    'completed'
    CANCELLED = 'CANCELLED'
    'cancelled'


class ActionTimelinessIdentifier(str, Enum):
    """An enumeration."""

    OPTIMAL = 'OPTIMAL'
    ACCEPTABLE = 'ACCEPTABLE'
    LATE = 'LATE'
    STALE = 'STALE'


class ActionVisibility(str, Enum):
    """An enumeration."""

    INTERNAL = 'INTERNAL'
    'Internal'
    PUBLIC = 'PUBLIC'
    'Public'


class AttributeTypeFormat(str, Enum):
    """An enumeration."""

    ORDERED_CHOICE = 'ORDERED_CHOICE'
    'Ordered choice'
    OPTIONAL_CHOICE = 'OPTIONAL_CHOICE'
    'Optional choice with optional text'
    UNORDERED_CHOICE = 'UNORDERED_CHOICE'
    'Choice'
    TEXT = 'TEXT'
    'Text'
    RICH_TEXT = 'RICH_TEXT'
    'Rich text'
    NUMERIC = 'NUMERIC'
    'Numeric'
    CATEGORY_CHOICE = 'CATEGORY_CHOICE'
    'Category'


class Comparison(str, Enum):
    """An enumeration."""

    LTE = 'LTE'
    GT = 'GT'


class PlanFeaturesContactPersonsPublicData(str, Enum):
    """An enumeration."""

    NONE = 'NONE'
    'Do not show contact persons publicly'
    NAME = 'NAME'
    'Show only name, role and affiliation'
    ALL = 'ALL'
    'Show all information'
    ALL_FOR_AUTHENTICATED = 'ALL_FOR_AUTHENTICATED'
    'Show all information but only for authenticated users'


class Sentiment(str, Enum):
    """An enumeration."""

    POSITIVE = 'POSITIVE'
    NEGATIVE = 'NEGATIVE'
    NEUTRAL = 'NEUTRAL'


class ActionAttributeValueInput(InputTypeModel):
    """No documentation."""

    attribute_type_id: str = Field(alias='attributeTypeId')
    choice_id: str = Field(alias='choiceId')


class ActionInput(InputTypeModel):
    """One action/measure tracked in an action plan."""

    name: str
    plan_id: str = Field(alias='planId')
    identifier: str
    'The identifier for this action (e.g. number)'
    description: str | None = None
    'What does this action involve in more detail?'
    primary_org_id: str | None = Field(alias='primaryOrgId', default=None)
    category_ids: list[str] | None = Field(alias='categoryIds', default=None)
    attribute_values: list[ActionAttributeValueInput] | None = Field(alias='attributeValues', default=None)


class AddRelatedOrganizationInput(InputTypeModel):
    """No documentation."""

    plan_id: str = Field(alias='planId')
    'The pk or identifier of the plan.'
    organization_id: str = Field(alias='organizationId')
    'The pk of the organization.'


class AttributeTypeInput(InputTypeModel):
    """AttributeType(id, latest_revision, order, instances_editable_by, instances_visible_for, primary_language_lowercase, object_content_type, scope_content_type, scope_id, name, identifier, help_text, format, unit, attribute_category_type, show_choice_names, has_zero_option, max_length, show_in_reporting_tab, primary_language, other_languages, i18n)."""

    plan_id: str = Field(alias='planId')
    identifier: str
    name: str
    format: AttributeTypeFormat
    'The format of the attributes with this type.'
    help_text: str | None = Field(alias='helpText', default=None)
    unit_id: str | None = Field(alias='unitId', default=None)
    choice_options: list['ChoiceOptionInput'] | None = Field(alias='choiceOptions', default=None)


class CategoryInput(InputTypeModel):
    """A category for actions and indicators."""

    type_id: str = Field(alias='typeId')
    identifier: str
    name: str
    parent_id: str | None = Field(alias='parentId', default=None)
    order: int | None = None


class CategoryTypeInput(InputTypeModel):
    """
    Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    plan_id: str = Field(alias='planId')
    identifier: str
    name: str
    select_widget: str | None = Field(alias='selectWidget', default=None)
    'Choose "Multiple" only if more than one category can be selected at a time, otherwise choose "Single" which is the default.'
    usable_for_actions: bool | None = Field(alias='usableForActions', default=None)
    usable_for_indicators: bool | None = Field(alias='usableForIndicators', default=None)
    editable_for_actions: bool | None = Field(alias='editableForActions', default=None)
    hide_category_identifiers: bool | None = Field(alias='hideCategoryIdentifiers', default=None)
    'Set if the categories do not have meaningful identifiers'
    primary_action_classification: bool = Field(alias='primaryActionClassification')
    'Whether this category type is the primary action classification. NOTE: A Plan must have exactly one primary action classification.'


class ChoiceOptionInput(InputTypeModel):
    """No documentation."""

    identifier: str
    name: str
    order: int


class OrganizationInput(InputTypeModel):
    """No documentation."""

    name: str
    'The official name of the organization.'
    abbreviation: str | None = None
    'Short abbreviation (e.g. "NASA", "YM").'
    parent_id: str | None = Field(alias='parentId', default=None)
    'ID of the parent organization. Omit for a root organization.'


class PlanFeaturesInput(InputTypeModel):
    """PlanFeatures(id, latest_revision, plan, allow_images_for_actions, show_admin_link, allow_public_site_login, expose_unpublished_plan_only_to_authenticated_user, contact_persons_public_data, contact_persons_show_picture, contact_persons_show_organization_ancestors, contact_persons_hide_moderators, has_action_identifiers, show_action_identifiers, has_action_contact_person_roles, minimal_statuses, has_action_official_name, has_action_lead_paragraph, has_action_primary_orgs, enable_search, enable_indicator_comparison, indicator_ordering, moderation_workflow, display_field_visibility_restrictions, output_report_action_print_layout, password_protected, indicators_open_in_modal, enable_change_log, enable_community_engagement, admin_accessibility_conformance_level)."""

    has_action_identifiers: bool | None = Field(alias='hasActionIdentifiers', default=None)
    'Set if the plan uses meaningful action identifiers'
    has_action_official_name: bool | None = Field(alias='hasActionOfficialName', default=None)
    'Set if the plan uses the official name field'
    has_action_lead_paragraph: bool | None = Field(alias='hasActionLeadParagraph', default=None)
    'Set if the plan uses the lead paragraph field'
    has_action_primary_orgs: bool | None = Field(alias='hasActionPrimaryOrgs', default=None)
    'Set if actions have a clear primary organization (such as multi-city plans)'


class PlanInput(InputTypeModel):
    """
    The Action Plan under monitoring.

    Most information in this service is linked to a Plan.
    """

    name: str
    'The official plan name in full form'
    identifier: str
    'A unique identifier for the plan used internally to distinguish between plans. This becomes part of the test site URL: https://[identifier].watch-test.kausal.tech. Use lowercase letters and dashes.'
    organization_id: str = Field(alias='organizationId')
    'The main organization for the plan'
    primary_language: str = Field(alias='primaryLanguage')
    'Primary language code (ISO 639-1, e.g. "en-US", "fi", "de-CH").'
    short_name: str | None = Field(alias='shortName', default=None)
    'A shorter version of the plan name'
    other_languages: list[str] = Field(alias='otherLanguages')
    'Additional language codes (ISO 639-1).'
    theme_identifier: str | None = Field(alias='themeIdentifier', default=None)
    features: PlanFeaturesInput | None = None


class MCPUserDetailsMe(OperationModel):
    """A user of the system."""

    typename: Literal['User'] = Field(alias='__typename', default='User')
    id: str
    uuid: str
    email: str
    first_name: str = Field(alias='firstName')
    last_name: str = Field(alias='lastName')
    is_superuser: bool = Field(alias='isSuperuser')
    'Designates that this user has all permissions without explicitly assigning them.'


class MCPUserDetails(OperationModel):
    """No documentation found for this operation."""

    me: MCPUserDetailsMe | None = Field(default=None)
    'The current user'

    class Arguments(ArgumentsModel):
        """Arguments for MCPUserDetails."""

        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPUserDetails."""

        document = 'query MCPUserDetails {\n  me {\n    id\n    uuid\n    email\n    firstName\n    lastName\n    isSuperuser\n    __typename\n  }\n}'


class MCPListPlansPlansOrganization(OperationModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'


class MCPListPlansPlans(OperationModel):
    """
    The Action Plan under monitoring.

    Most information in this service is linked to a Plan.
    """

    typename: Literal['Plan'] = Field(alias='__typename', default='Plan')
    id: str
    identifier: str
    'A unique identifier for the plan used internally to distinguish between plans. This becomes part of the test site URL: https://[identifier].watch-test.kausal.tech. Use lowercase letters and dashes.'
    name: str
    'The official plan name in full form'
    short_name: str | None = Field(default=None, alias='shortName')
    'A shorter version of the plan name'
    version_name: str = Field(alias='versionName')
    'If this plan has multiple versions, name of this version'
    primary_language: str = Field(alias='primaryLanguage')
    other_languages: list[str] = Field(alias='otherLanguages')
    published_at: datetime | None = Field(default=None, alias='publishedAt')
    view_url: str | None = Field(default=None, alias='viewUrl')
    organization: MCPListPlansPlansOrganization
    'The main organization for the plan'


class MCPListPlans(OperationModel):
    """No documentation found for this operation."""

    plans: list[MCPListPlansPlans] | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPListPlans."""

        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPListPlans."""

        document = 'query MCPListPlans {\n  plans {\n    id\n    identifier\n    name\n    shortName\n    versionName\n    primaryLanguage\n    otherLanguages\n    publishedAt\n    viewUrl\n    organization {\n      id\n      name\n      __typename\n    }\n    __typename\n  }\n}'


class MCPListActionsPlanactionsStatus(OperationModel):
    """The current status for the action ("on time", "late", "completed", etc.)."""

    typename: Literal['ActionStatus'] = Field(alias='__typename', default='ActionStatus')
    id: str
    identifier: str
    name: str
    is_completed: bool = Field(alias='isCompleted')


class MCPListActionsPlanactionsImplementationphase(OperationModel):
    """No documentation."""

    typename: Literal['ActionImplementationPhase'] = Field(alias='__typename', default='ActionImplementationPhase')
    id: str
    identifier: str
    name: str


class MCPListActionsPlanactionsStatussummary(OperationModel):
    """No documentation."""

    typename: Literal['ActionStatusSummary'] = Field(alias='__typename', default='ActionStatusSummary')
    identifier: ActionStatusSummaryIdentifier
    label: str
    sentiment: Sentiment
    is_active: bool = Field(alias='isActive')
    is_completed: bool = Field(alias='isCompleted')


class MCPListActionsPlanactionsResponsiblepartiesOrganization(OperationModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'
    abbreviation: str | None = Field(default=None)
    'Short version or abbreviation of the organization name to be displayed when it is not necessary to show the full name'


class MCPListActionsPlanactionsResponsibleparties(OperationModel):
    """No documentation."""

    typename: Literal['ActionResponsibleParty'] = Field(alias='__typename', default='ActionResponsibleParty')
    id: str
    organization: MCPListActionsPlanactionsResponsiblepartiesOrganization


class MCPListActionsPlanactionsPrimaryorg(OperationModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'
    abbreviation: str | None = Field(default=None)
    'Short version or abbreviation of the organization name to be displayed when it is not necessary to show the full name'


class MCPListActionsPlanactionsCategoriesType(OperationModel):
    """
    Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    typename: Literal['CategoryType'] = Field(alias='__typename', default='CategoryType')
    id: str
    identifier: str
    name: str


class MCPListActionsPlanactionsCategories(OperationModel):
    """A category for actions and indicators."""

    typename: Literal['Category'] = Field(alias='__typename', default='Category')
    id: str
    identifier: str
    name: str
    type: MCPListActionsPlanactionsCategoriesType


class MCPListActionsPlanactions(OperationModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str
    official_name: str | None = Field(default=None, alias='officialName')
    'The name as approved by an official party'
    completion: int | None = Field(default=None)
    'The completion percentage for this action'
    schedule_continuous: bool = Field(alias='scheduleContinuous')
    'Set if the action does not have a start or an end date'
    start_date: str | None = Field(default=None, alias='startDate')
    'The date when implementation of this action starts'
    end_date: str | None = Field(default=None, alias='endDate')
    'The date when implementation of this action ends'
    updated_at: datetime = Field(alias='updatedAt')
    status: MCPListActionsPlanactionsStatus | None = Field(default=None)
    implementation_phase: MCPListActionsPlanactionsImplementationphase | None = Field(default=None, alias='implementationPhase')
    status_summary: MCPListActionsPlanactionsStatussummary = Field(alias='statusSummary')
    responsible_parties: list[MCPListActionsPlanactionsResponsibleparties] = Field(alias='responsibleParties')
    primary_org: MCPListActionsPlanactionsPrimaryorg | None = Field(default=None, alias='primaryOrg')
    categories: list[MCPListActionsPlanactionsCategories]


class MCPListActions(OperationModel):
    """No documentation found for this operation."""

    plan_actions: list[MCPListActionsPlanactions] | None = Field(default=None, alias='planActions')

    class Arguments(ArgumentsModel):
        """Arguments for MCPListActions."""

        plan: str
        category: str | None = Field(default=None)
        first: int | None = Field(default=None)
        order_by: str | None = Field(alias='orderBy', default=None)
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPListActions."""

        document = 'query MCPListActions($plan: ID!, $category: ID, $first: Int, $orderBy: String) @context(input: {identifier: $plan}) {\n  planActions(plan: $plan, category: $category, first: $first, orderBy: $orderBy) {\n    id\n    identifier\n    name\n    officialName\n    completion\n    scheduleContinuous\n    startDate\n    endDate\n    updatedAt\n    status {\n      id\n      identifier\n      name\n      isCompleted\n      __typename\n    }\n    implementationPhase {\n      id\n      identifier\n      name\n      __typename\n    }\n    statusSummary {\n      identifier\n      label\n      sentiment\n      isActive\n      isCompleted\n      __typename\n    }\n    responsibleParties {\n      id\n      organization {\n        id\n        name\n        abbreviation\n        __typename\n      }\n      __typename\n    }\n    primaryOrg {\n      id\n      name\n      abbreviation\n      __typename\n    }\n    categories {\n      id\n      identifier\n      name\n      type {\n        id\n        identifier\n        name\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}'


class MCPGetPlanPlanFeatures(OperationModel):
    """No documentation."""

    typename: Literal['PlanFeatures'] = Field(alias='__typename', default='PlanFeatures')
    public_contact_persons: bool = Field(alias='publicContactPersons')
    has_action_identifiers: bool = Field(alias='hasActionIdentifiers')
    'Set if the plan uses meaningful action identifiers'
    has_action_official_name: bool = Field(alias='hasActionOfficialName')
    'Set if the plan uses the official name field'
    has_action_lead_paragraph: bool = Field(alias='hasActionLeadParagraph')
    'Set if the plan uses the lead paragraph field'
    has_action_primary_orgs: bool = Field(alias='hasActionPrimaryOrgs')
    'Set if actions have a clear primary organization (such as multi-city plans)'
    enable_search: bool = Field(alias='enableSearch')
    'Enable site-wide search functionality'
    enable_indicator_comparison: bool = Field(alias='enableIndicatorComparison')
    'Set to enable comparing indicators between organizations'
    minimal_statuses: bool = Field(alias='minimalStatuses')
    "Set to prevent showing status-specific graphs and other elements if statuses aren't systematically used in this action plan"
    contact_persons_public_data: PlanFeaturesContactPersonsPublicData = Field(alias='contactPersonsPublicData')
    'Choose which information about contact persons is visible in the public UI'


class MCPGetPlanPlanCategorytypes(OperationModel):
    """
    Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    typename: Literal['CategoryType'] = Field(alias='__typename', default='CategoryType')
    id: str
    identifier: str
    name: str
    usable_for_actions: bool = Field(alias='usableForActions')
    usable_for_indicators: bool = Field(alias='usableForIndicators')


class MCPGetPlanPlanActionstatussummaries(OperationModel):
    """No documentation."""

    typename: Literal['ActionStatusSummary'] = Field(alias='__typename', default='ActionStatusSummary')
    identifier: ActionStatusSummaryIdentifier
    label: str
    is_active: bool = Field(alias='isActive')
    is_completed: bool = Field(alias='isCompleted')
    sentiment: Sentiment


class MCPGetPlanPlanActionattributetypesUnit(OperationModel):
    """No documentation."""

    typename: Literal['Unit'] = Field(alias='__typename', default='Unit')
    id: str
    short_name: str | None = Field(default=None, alias='shortName')


class MCPGetPlanPlanActionattributetypesChoiceoptions(OperationModel):
    """No documentation."""

    typename: Literal['AttributeTypeChoiceOption'] = Field(alias='__typename', default='AttributeTypeChoiceOption')
    id: str
    identifier: str
    name: str


class MCPGetPlanPlanActionattributetypes(OperationModel):
    """No documentation."""

    typename: Literal['AttributeType'] = Field(alias='__typename', default='AttributeType')
    id: str
    identifier: str
    name: str
    format: AttributeTypeFormat
    unit: MCPGetPlanPlanActionattributetypesUnit | None = Field(default=None)
    choice_options: list[MCPGetPlanPlanActionattributetypesChoiceoptions] = Field(alias='choiceOptions')


class MCPGetPlanPlan(OperationModel):
    """
    The Action Plan under monitoring.

    Most information in this service is linked to a Plan.
    """

    typename: Literal['Plan'] = Field(alias='__typename', default='Plan')
    id: str
    identifier: str
    'A unique identifier for the plan used internally to distinguish between plans. This becomes part of the test site URL: https://[identifier].watch-test.kausal.tech. Use lowercase letters and dashes.'
    name: str
    'The official plan name in full form'
    short_name: str | None = Field(default=None, alias='shortName')
    'A shorter version of the plan name'
    version_name: str = Field(alias='versionName')
    'If this plan has multiple versions, name of this version'
    primary_language: str = Field(alias='primaryLanguage')
    other_languages: list[str] = Field(alias='otherLanguages')
    published_at: datetime | None = Field(default=None, alias='publishedAt')
    view_url: str | None = Field(default=None, alias='viewUrl')
    accessibility_statement_url: str | None = Field(default=None, alias='accessibilityStatementUrl')
    external_feedback_url: str | None = Field(default=None, alias='externalFeedbackUrl')
    "If not empty, the system's built-in user feedback feature will be replaced by a link to an external feedback form available at this web address."
    features: MCPGetPlanPlanFeatures
    category_types: list[MCPGetPlanPlanCategorytypes] = Field(alias='categoryTypes')
    action_status_summaries: list[MCPGetPlanPlanActionstatussummaries] = Field(alias='actionStatusSummaries')
    action_attribute_types: list[MCPGetPlanPlanActionattributetypes] = Field(alias='actionAttributeTypes')


class MCPGetPlan(OperationModel):
    """No documentation found for this operation."""

    plan: MCPGetPlanPlan | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPGetPlan."""

        identifier: str
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPGetPlan."""

        document = 'query MCPGetPlan($identifier: ID!) @context(input: {identifier: $identifier}) {\n  plan(id: $identifier) {\n    id\n    identifier\n    name\n    shortName\n    versionName\n    primaryLanguage\n    otherLanguages\n    publishedAt\n    viewUrl\n    accessibilityStatementUrl\n    externalFeedbackUrl\n    features {\n      publicContactPersons\n      hasActionIdentifiers\n      hasActionOfficialName\n      hasActionLeadParagraph\n      hasActionPrimaryOrgs\n      enableSearch\n      enableIndicatorComparison\n      minimalStatuses\n      contactPersonsPublicData\n      __typename\n    }\n    categoryTypes {\n      id\n      identifier\n      name\n      usableForActions\n      usableForIndicators\n      __typename\n    }\n    actionStatusSummaries {\n      identifier\n      label\n      isActive\n      isCompleted\n      sentiment\n      __typename\n    }\n    actionAttributeTypes {\n      id\n      identifier\n      name\n      format\n      unit {\n        id\n        shortName\n        __typename\n      }\n      choiceOptions {\n        id\n        identifier\n        name\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}'


class MCPListOrganizationsAdminOrganizationsParent(OperationModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str


class MCPListOrganizationsAdminOrganizations(OperationModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'
    abbreviation: str | None = Field(default=None)
    'Short version or abbreviation of the organization name to be displayed when it is not necessary to show the full name'
    parent: MCPListOrganizationsAdminOrganizationsParent | None = Field(default=None)


class MCPListOrganizationsAdmin(OperationModel):
    """No documentation."""

    typename: Literal['AdminQuery'] = Field(alias='__typename', default='AdminQuery')
    organizations: list[MCPListOrganizationsAdminOrganizations]
    'List of all organizations'


class MCPListOrganizations(OperationModel):
    """No documentation found for this operation."""

    admin: MCPListOrganizationsAdmin
    'Admin query namespace'

    class Arguments(ArgumentsModel):
        """Arguments for MCPListOrganizations."""

        plan: str | None = Field(default=None)
        parent: str | None = Field(default=None)
        depth: int | None = Field(default=None)
        contains: str | None = Field(default=None)
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPListOrganizations."""

        document = 'query MCPListOrganizations($plan: ID, $parent: ID, $depth: Int, $contains: String) {\n  admin {\n    organizations(plan: $plan, parent: $parent, depth: $depth, contains: $contains) {\n      id\n      name\n      abbreviation\n      parent {\n        id\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}'


class MCPCreateOrganizationOrganizationCreateorganizationParent(OperationModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str


class MCPCreateOrganizationOrganizationCreateorganization(OperationModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'
    abbreviation: str | None = Field(default=None)
    'Short version or abbreviation of the organization name to be displayed when it is not necessary to show the full name'
    parent: MCPCreateOrganizationOrganizationCreateorganizationParent | None = Field(default=None)


class MCPCreateOrganizationOrganization(OperationModel):
    """No documentation."""

    typename: Literal['OrganizationMutations'] = Field(alias='__typename', default='OrganizationMutations')
    create_organization: MCPCreateOrganizationOrganizationCreateorganization = Field(alias='createOrganization')
    'Create a new organization'


class MCPCreateOrganization(OperationModel):
    """No documentation found for this operation."""

    organization: MCPCreateOrganizationOrganization | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreateOrganization."""

        input: OrganizationInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreateOrganization."""

        document = 'mutation MCPCreateOrganization($input: OrganizationInput!) {\n  organization {\n    createOrganization(input: $input) {\n      id\n      name\n      abbreviation\n      parent {\n        id\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}'


class MCPCreatePlanPlanCreateplan(OperationModel):
    """
    The Action Plan under monitoring.

    Most information in this service is linked to a Plan.
    """

    typename: Literal['Plan'] = Field(alias='__typename', default='Plan')
    id: str
    identifier: str
    'A unique identifier for the plan used internally to distinguish between plans. This becomes part of the test site URL: https://[identifier].watch-test.kausal.tech. Use lowercase letters and dashes.'
    name: str
    'The official plan name in full form'
    short_name: str | None = Field(default=None, alias='shortName')
    'A shorter version of the plan name'
    version_name: str = Field(alias='versionName')
    'If this plan has multiple versions, name of this version'
    primary_language: str = Field(alias='primaryLanguage')
    other_languages: list[str] = Field(alias='otherLanguages')


class MCPCreatePlanPlan(OperationModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    create_plan: MCPCreatePlanPlanCreateplan = Field(alias='createPlan')
    'Create a new plan. Returns the newly created plan.'


class MCPCreatePlan(OperationModel):
    """No documentation found for this operation."""

    plan: MCPCreatePlanPlan | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreatePlan."""

        input: PlanInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreatePlan."""

        document = 'mutation MCPCreatePlan($input: PlanInput!) {\n  plan {\n    createPlan(input: $input) {\n      id\n      identifier\n      name\n      shortName\n      versionName\n      primaryLanguage\n      otherLanguages\n      __typename\n    }\n    __typename\n  }\n}'


class MCPAddRelatedOrganizationPlanAddrelatedorganization(OperationModel):
    """
    The Action Plan under monitoring.

    Most information in this service is linked to a Plan.
    """

    typename: Literal['Plan'] = Field(alias='__typename', default='Plan')
    id: str
    identifier: str
    'A unique identifier for the plan used internally to distinguish between plans. This becomes part of the test site URL: https://[identifier].watch-test.kausal.tech. Use lowercase letters and dashes.'
    name: str
    'The official plan name in full form'


class MCPAddRelatedOrganizationPlan(OperationModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    add_related_organization: MCPAddRelatedOrganizationPlanAddrelatedorganization = Field(alias='addRelatedOrganization')
    'Add a related organization to a plan'


class MCPAddRelatedOrganization(OperationModel):
    """No documentation found for this operation."""

    plan: MCPAddRelatedOrganizationPlan | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPAddRelatedOrganization."""

        input: AddRelatedOrganizationInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPAddRelatedOrganization."""

        document = 'mutation MCPAddRelatedOrganization($input: AddRelatedOrganizationInput!) {\n  plan {\n    addRelatedOrganization(input: $input) {\n      id\n      identifier\n      name\n      __typename\n    }\n    __typename\n  }\n}'


class MCPDeletePlanPlan(OperationModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    delete_plan: bool = Field(alias='deletePlan')
    'Delete a recently created plan (must be < 2 days old)'


class MCPDeletePlan(OperationModel):
    """No documentation found for this operation."""

    plan: MCPDeletePlanPlan | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPDeletePlan."""

        id: str
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPDeletePlan."""

        document = 'mutation MCPDeletePlan($id: ID!) {\n  plan {\n    deletePlan(id: $id)\n    __typename\n  }\n}'


class MCPCreateActionActionCreateactionPrimaryorg(OperationModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'


class MCPCreateActionActionCreateactionCategoriesType(OperationModel):
    """
    Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    typename: Literal['CategoryType'] = Field(alias='__typename', default='CategoryType')
    identifier: str


class MCPCreateActionActionCreateactionCategories(OperationModel):
    """A category for actions and indicators."""

    typename: Literal['Category'] = Field(alias='__typename', default='Category')
    id: str
    identifier: str
    name: str
    type: MCPCreateActionActionCreateactionCategoriesType


class MCPCreateActionActionCreateactionAttributesType(OperationModel):
    """No documentation."""

    typename: Literal['AttributeType'] = Field(alias='__typename', default='AttributeType')
    identifier: str


class MCPCreateActionActionCreateactionAttributesChoice(OperationModel):
    """No documentation."""

    typename: Literal['AttributeTypeChoiceOption'] = Field(alias='__typename', default='AttributeTypeChoiceOption')
    identifier: str
    name: str


class MCPCreateActionActionCreateactionAttributesBase(OperationModel):
    """No documentation."""


class MCPCreateActionActionCreateactionAttributesBaseAttributeCategoryChoice(
    MCPCreateActionActionCreateactionAttributesBase, OperationModel
):
    """No documentation."""

    typename: Literal['AttributeCategoryChoice'] = Field(alias='__typename', default='AttributeCategoryChoice')


class MCPCreateActionActionCreateactionAttributesBaseAttributeChoice(
    MCPCreateActionActionCreateactionAttributesBase, OperationModel
):
    """No documentation."""

    typename: Literal['AttributeChoice'] = Field(alias='__typename', default='AttributeChoice')
    type: MCPCreateActionActionCreateactionAttributesType
    choice: MCPCreateActionActionCreateactionAttributesChoice | None = Field(default=None)


class MCPCreateActionActionCreateactionAttributesBaseAttributeNumericValue(
    MCPCreateActionActionCreateactionAttributesBase, OperationModel
):
    """No documentation."""

    typename: Literal['AttributeNumericValue'] = Field(alias='__typename', default='AttributeNumericValue')


class MCPCreateActionActionCreateactionAttributesBaseAttributeRichText(
    MCPCreateActionActionCreateactionAttributesBase, OperationModel
):
    """No documentation."""

    typename: Literal['AttributeRichText'] = Field(alias='__typename', default='AttributeRichText')


class MCPCreateActionActionCreateactionAttributesBaseAttributeText(
    MCPCreateActionActionCreateactionAttributesBase, OperationModel
):
    """No documentation."""

    typename: Literal['AttributeText'] = Field(alias='__typename', default='AttributeText')


class MCPCreateActionActionCreateactionAttributesBaseCatchAll(MCPCreateActionActionCreateactionAttributesBase, OperationModel):
    """Catch all class for MCPCreateActionActionCreateactionAttributesBase."""

    typename: str = Field(alias='__typename')


class MCPCreateActionActionCreateaction(OperationModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str
    description: str | None = Field(default=None)
    'What does this action involve in more detail?'
    primary_org: MCPCreateActionActionCreateactionPrimaryorg | None = Field(default=None, alias='primaryOrg')
    categories: list[MCPCreateActionActionCreateactionCategories]
    attributes: list[
        Annotated[
            MCPCreateActionActionCreateactionAttributesBaseAttributeCategoryChoice
            | MCPCreateActionActionCreateactionAttributesBaseAttributeChoice
            | MCPCreateActionActionCreateactionAttributesBaseAttributeNumericValue
            | MCPCreateActionActionCreateactionAttributesBaseAttributeRichText
            | MCPCreateActionActionCreateactionAttributesBaseAttributeText,
            Field(discriminator='typename'),
        ]
        | MCPCreateActionActionCreateactionAttributesBaseCatchAll
    ]


class MCPCreateActionAction(OperationModel):
    """No documentation."""

    typename: Literal['ActionMutations'] = Field(alias='__typename', default='ActionMutations')
    create_action: MCPCreateActionActionCreateaction = Field(alias='createAction')


class MCPCreateAction(OperationModel):
    """No documentation found for this operation."""

    action: MCPCreateActionAction | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreateAction."""

        input: ActionInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreateAction."""

        document = 'mutation MCPCreateAction($input: ActionInput!) {\n  action {\n    createAction(input: $input) {\n      id\n      identifier\n      name\n      description\n      primaryOrg {\n        id\n        name\n        __typename\n      }\n      categories {\n        id\n        identifier\n        name\n        type {\n          identifier\n          __typename\n        }\n        __typename\n      }\n      attributes {\n        ... on AttributeChoice {\n          type {\n            identifier\n          }\n          choice {\n            identifier\n            name\n          }\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}'


class MCPCreateCategoryTypePlanCreatecategorytype(OperationModel):
    """
    Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    typename: Literal['CategoryType'] = Field(alias='__typename', default='CategoryType')
    id: str
    identifier: str
    name: str
    usable_for_actions: bool = Field(alias='usableForActions')
    usable_for_indicators: bool = Field(alias='usableForIndicators')


class MCPCreateCategoryTypePlan(OperationModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    create_category_type: MCPCreateCategoryTypePlanCreatecategorytype = Field(alias='createCategoryType')
    'Create a new category type. Returns the newly created category type.'


class MCPCreateCategoryType(OperationModel):
    """No documentation found for this operation."""

    plan: MCPCreateCategoryTypePlan | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreateCategoryType."""

        input: CategoryTypeInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreateCategoryType."""

        document = 'mutation MCPCreateCategoryType($input: CategoryTypeInput!) {\n  plan {\n    createCategoryType(input: $input) {\n      id\n      identifier\n      name\n      usableForActions\n      usableForIndicators\n      __typename\n    }\n    __typename\n  }\n}'


class MCPCreateCategoryPlanCreatecategoryParent(OperationModel):
    """A category for actions and indicators."""

    typename: Literal['Category'] = Field(alias='__typename', default='Category')
    id: str


class MCPCreateCategoryPlanCreatecategory(OperationModel):
    """A category for actions and indicators."""

    typename: Literal['Category'] = Field(alias='__typename', default='Category')
    id: str
    identifier: str
    name: str
    parent: MCPCreateCategoryPlanCreatecategoryParent | None = Field(default=None)
    order: int


class MCPCreateCategoryPlan(OperationModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    create_category: MCPCreateCategoryPlanCreatecategory = Field(alias='createCategory')
    'Create a new category. Returns the newly created category.'


class MCPCreateCategory(OperationModel):
    """No documentation found for this operation."""

    plan: MCPCreateCategoryPlan | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreateCategory."""

        input: CategoryInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreateCategory."""

        document = 'mutation MCPCreateCategory($input: CategoryInput!) {\n  plan {\n    createCategory(input: $input) {\n      id\n      identifier\n      name\n      parent {\n        id\n        __typename\n      }\n      order\n      __typename\n    }\n    __typename\n  }\n}'


class MCPCreateAttributeTypePlanCreateattributetypeUnit(OperationModel):
    """No documentation."""

    typename: Literal['Unit'] = Field(alias='__typename', default='Unit')
    id: str
    short_name: str | None = Field(default=None, alias='shortName')


class MCPCreateAttributeTypePlanCreateattributetypeChoiceoptions(OperationModel):
    """No documentation."""

    typename: Literal['AttributeTypeChoiceOption'] = Field(alias='__typename', default='AttributeTypeChoiceOption')
    id: str
    identifier: str
    name: str


class MCPCreateAttributeTypePlanCreateattributetype(OperationModel):
    """No documentation."""

    typename: Literal['AttributeType'] = Field(alias='__typename', default='AttributeType')
    id: str
    identifier: str
    name: str
    format: AttributeTypeFormat
    help_text: str = Field(alias='helpText')
    unit: MCPCreateAttributeTypePlanCreateattributetypeUnit | None = Field(default=None)
    choice_options: list[MCPCreateAttributeTypePlanCreateattributetypeChoiceoptions] = Field(alias='choiceOptions')


class MCPCreateAttributeTypePlan(OperationModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    create_attribute_type: MCPCreateAttributeTypePlanCreateattributetype = Field(alias='createAttributeType')


class MCPCreateAttributeType(OperationModel):
    """No documentation found for this operation."""

    plan: MCPCreateAttributeTypePlan | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreateAttributeType."""

        input: AttributeTypeInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreateAttributeType."""

        document = 'mutation MCPCreateAttributeType($input: AttributeTypeInput!) {\n  plan {\n    createAttributeType(input: $input) {\n      id\n      identifier\n      name\n      format\n      helpText\n      unit {\n        id\n        shortName\n        __typename\n      }\n      choiceOptions {\n        id\n        identifier\n        name\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}'


class MCPGetActionsAdminActionsStatus(OperationModel):
    """The current status for the action ("on time", "late", "completed", etc.)."""

    typename: Literal['ActionStatus'] = Field(alias='__typename', default='ActionStatus')
    id: str
    identifier: str
    name: str
    is_completed: bool = Field(alias='isCompleted')


class MCPGetActionsAdminActionsImplementationphase(OperationModel):
    """No documentation."""

    typename: Literal['ActionImplementationPhase'] = Field(alias='__typename', default='ActionImplementationPhase')
    id: str
    identifier: str
    name: str


class MCPGetActionsAdminActionsStatussummary(OperationModel):
    """No documentation."""

    typename: Literal['ActionStatusSummary'] = Field(alias='__typename', default='ActionStatusSummary')
    identifier: ActionStatusSummaryIdentifier
    label: str
    sentiment: Sentiment
    is_active: bool = Field(alias='isActive')
    is_completed: bool = Field(alias='isCompleted')


class MCPGetActionsAdminActionsTimeliness(OperationModel):
    """No documentation."""

    typename: Literal['ActionTimeliness'] = Field(alias='__typename', default='ActionTimeliness')
    identifier: ActionTimelinessIdentifier
    comparison: Comparison
    days: int


class MCPGetActionsAdminActionsImpact(OperationModel):
    """An impact classification for an action in an action plan."""

    typename: Literal['ActionImpact'] = Field(alias='__typename', default='ActionImpact')
    id: str
    identifier: str
    name: str


class MCPGetActionsAdminActionsPrimaryorg(OperationModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'
    abbreviation: str | None = Field(default=None)
    'Short version or abbreviation of the organization name to be displayed when it is not necessary to show the full name'


class MCPGetActionsAdminActionsResponsiblepartiesOrganization(OperationModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'
    abbreviation: str | None = Field(default=None)
    'Short version or abbreviation of the organization name to be displayed when it is not necessary to show the full name'


class MCPGetActionsAdminActionsResponsibleparties(OperationModel):
    """No documentation."""

    typename: Literal['ActionResponsibleParty'] = Field(alias='__typename', default='ActionResponsibleParty')
    id: str
    role: ActionResponsiblePartyRole | None = Field(default=None)
    specifier: str
    'The responsibility domain for the organization'
    organization: MCPGetActionsAdminActionsResponsiblepartiesOrganization


class MCPGetActionsAdminActionsCategoriesType(OperationModel):
    """
    Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    typename: Literal['CategoryType'] = Field(alias='__typename', default='CategoryType')
    id: str
    identifier: str
    name: str


class MCPGetActionsAdminActionsCategories(OperationModel):
    """A category for actions and indicators."""

    typename: Literal['Category'] = Field(alias='__typename', default='Category')
    id: str
    identifier: str
    name: str
    type: MCPGetActionsAdminActionsCategoriesType


class MCPGetActionsAdminActionsContactpersonsPersonOrganization(OperationModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'
    abbreviation: str | None = Field(default=None)
    'Short version or abbreviation of the organization name to be displayed when it is not necessary to show the full name'


class MCPGetActionsAdminActionsContactpersonsPerson(OperationModel):
    """No documentation."""

    typename: Literal['Person'] = Field(alias='__typename', default='Person')
    id: str
    first_name: str = Field(alias='firstName')
    last_name: str = Field(alias='lastName')
    title: str | None = Field(default=None)
    'Job title or role of this person'
    email: str
    organization: MCPGetActionsAdminActionsContactpersonsPersonOrganization


class MCPGetActionsAdminActionsContactpersons(OperationModel):
    """A Person acting as a contact for an action."""

    typename: Literal['ActionContactPerson'] = Field(alias='__typename', default='ActionContactPerson')
    id: str
    role: ActionContactPersonRole
    primary_contact: bool = Field(alias='primaryContact')
    'Is this person the primary contact person for the action?'
    person: MCPGetActionsAdminActionsContactpersonsPerson


class MCPGetActionsAdminActionsTasks(OperationModel):
    """
    A task that should be completed during the execution of an action.

    The task will have at least a name and an estimate of the due date.
    """

    typename: Literal['ActionTask'] = Field(alias='__typename', default='ActionTask')
    id: str
    name: str
    state: ActionTaskState
    due_at: str = Field(alias='dueAt')
    'The date by which the task should be completed (deadline)'
    completed_at: str | None = Field(default=None, alias='completedAt')
    'The date when the task was completed'
    comment: str | None = Field(default=None)


class MCPGetActionsAdminActionsRelatedindicatorsIndicatorUnit(OperationModel):
    """No documentation."""

    typename: Literal['Unit'] = Field(alias='__typename', default='Unit')
    id: str
    name: str
    short_name: str | None = Field(default=None, alias='shortName')


class MCPGetActionsAdminActionsRelatedindicatorsIndicatorLatestvalue(OperationModel):
    """One measurement of an indicator for a certain date/month/year."""

    typename: Literal['IndicatorValue'] = Field(alias='__typename', default='IndicatorValue')
    id: str
    date: str | None = Field(default=None)
    value: float


class MCPGetActionsAdminActionsRelatedindicatorsIndicator(OperationModel):
    """An indicator with which to measure actions and progress towards strategic goals."""

    typename: Literal['Indicator'] = Field(alias='__typename', default='Indicator')
    id: str
    identifier: str | None = Field(default=None)
    name: str
    unit: MCPGetActionsAdminActionsRelatedindicatorsIndicatorUnit
    latest_value: MCPGetActionsAdminActionsRelatedindicatorsIndicatorLatestvalue | None = Field(default=None, alias='latestValue')


class MCPGetActionsAdminActionsRelatedindicators(OperationModel):
    """Link between an action and an indicator."""

    typename: Literal['ActionIndicator'] = Field(alias='__typename', default='ActionIndicator')
    id: str
    effect_type: ActionIndicatorEffectType = Field(alias='effectType')
    'What type of effect should the action cause?'
    indicates_action_progress: bool = Field(alias='indicatesActionProgress')
    'Set if the indicator should be used to determine action progress'
    indicator: MCPGetActionsAdminActionsRelatedindicatorsIndicator


class MCPGetActionsAdminActionsLinks(OperationModel):
    """A link related to an action."""

    typename: Literal['ActionLink'] = Field(alias='__typename', default='ActionLink')
    id: str
    url: str
    title: str


class MCPGetActionsAdminActionsStatusupdatesAuthor(OperationModel):
    """No documentation."""

    typename: Literal['Person'] = Field(alias='__typename', default='Person')
    id: str
    first_name: str = Field(alias='firstName')
    last_name: str = Field(alias='lastName')


class MCPGetActionsAdminActionsStatusupdates(OperationModel):
    """No documentation."""

    typename: Literal['ActionStatusUpdate'] = Field(alias='__typename', default='ActionStatusUpdate')
    id: str
    title: str
    date: str
    content: str
    author: MCPGetActionsAdminActionsStatusupdatesAuthor | None = Field(default=None)


class MCPGetActionsAdminActionsRelatedactions(OperationModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class MCPGetActionsAdminActionsMergedwith(OperationModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class MCPGetActionsAdminActionsMergedactions(OperationModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class MCPGetActionsAdminActionsSupersededby(OperationModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class MCPGetActionsAdminActionsSupersededactions(OperationModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class MCPGetActionsAdminActionsAlldependencyrelationshipsPreceding(OperationModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class MCPGetActionsAdminActionsAlldependencyrelationshipsDependent(OperationModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class MCPGetActionsAdminActionsAlldependencyrelationships(OperationModel):
    """No documentation."""

    typename: Literal['ActionDependencyRelationship'] = Field(alias='__typename', default='ActionDependencyRelationship')
    preceding: MCPGetActionsAdminActionsAlldependencyrelationshipsPreceding
    dependent: MCPGetActionsAdminActionsAlldependencyrelationshipsDependent


class MCPGetActionsAdminActionsAttributesTypeUnit(OperationModel):
    """No documentation."""

    typename: Literal['Unit'] = Field(alias='__typename', default='Unit')
    short_name: str | None = Field(default=None, alias='shortName')


class MCPGetActionsAdminActionsAttributesType(OperationModel):
    """No documentation."""

    typename: Literal['AttributeType'] = Field(alias='__typename', default='AttributeType')
    identifier: str
    name: str
    unit: MCPGetActionsAdminActionsAttributesTypeUnit | None = Field(default=None)


class MCPGetActionsAdminActionsAttributesCategoriesType(OperationModel):
    """
    Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    typename: Literal['CategoryType'] = Field(alias='__typename', default='CategoryType')
    identifier: str


class MCPGetActionsAdminActionsAttributesCategories(OperationModel):
    """A category for actions and indicators."""

    typename: Literal['Category'] = Field(alias='__typename', default='Category')
    identifier: str
    type: MCPGetActionsAdminActionsAttributesCategoriesType


class MCPGetActionsAdminActionsAttributesChoice(OperationModel):
    """No documentation."""

    typename: Literal['AttributeTypeChoiceOption'] = Field(alias='__typename', default='AttributeTypeChoiceOption')
    identifier: str


class MCPGetActionsAdminActionsAttributesBase(OperationModel):
    """No documentation."""

    type: MCPGetActionsAdminActionsAttributesType
    key_identifier: str = Field(alias='keyIdentifier')


class MCPGetActionsAdminActionsAttributesBaseAttributeCategoryChoice(MCPGetActionsAdminActionsAttributesBase, OperationModel):
    """No documentation."""

    typename: Literal['AttributeCategoryChoice'] = Field(alias='__typename', default='AttributeCategoryChoice')
    categories: list[MCPGetActionsAdminActionsAttributesCategories]


class MCPGetActionsAdminActionsAttributesBaseAttributeChoice(MCPGetActionsAdminActionsAttributesBase, OperationModel):
    """No documentation."""

    typename: Literal['AttributeChoice'] = Field(alias='__typename', default='AttributeChoice')
    choice: MCPGetActionsAdminActionsAttributesChoice | None = Field(default=None)


class MCPGetActionsAdminActionsAttributesBaseAttributeNumericValue(MCPGetActionsAdminActionsAttributesBase, OperationModel):
    """No documentation."""

    typename: Literal['AttributeNumericValue'] = Field(alias='__typename', default='AttributeNumericValue')
    numeric_value: float = Field(alias='numericValue')


class MCPGetActionsAdminActionsAttributesBaseAttributeRichText(MCPGetActionsAdminActionsAttributesBase, OperationModel):
    """No documentation."""

    typename: Literal['AttributeRichText'] = Field(alias='__typename', default='AttributeRichText')
    rich_text_value: str = Field(alias='richTextValue')


class MCPGetActionsAdminActionsAttributesBaseAttributeText(MCPGetActionsAdminActionsAttributesBase, OperationModel):
    """No documentation."""

    typename: Literal['AttributeText'] = Field(alias='__typename', default='AttributeText')
    text_value: str = Field(alias='textValue')


class MCPGetActionsAdminActionsAttributesBaseCatchAll(MCPGetActionsAdminActionsAttributesBase, OperationModel):
    """Catch all class for MCPGetActionsAdminActionsAttributesBase."""

    typename: str = Field(alias='__typename')


class MCPGetActionsAdminActions(OperationModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    uuid: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str
    official_name: str | None = Field(default=None, alias='officialName')
    'The name as approved by an official party'
    lead_paragraph: str = Field(alias='leadParagraph')
    description: str | None = Field(default=None)
    'What does this action involve in more detail?'
    start_date: str | None = Field(default=None, alias='startDate')
    'The date when implementation of this action starts'
    end_date: str | None = Field(default=None, alias='endDate')
    'The date when implementation of this action ends'
    schedule_continuous: bool = Field(alias='scheduleContinuous')
    'Set if the action does not have a start or an end date'
    date_format: ActionDateFormat | None = Field(default=None, alias='dateFormat')
    'Format of action start and end dates shown in the public UI.             The default for all actions can be specified on the actions page.'
    updated_at: datetime = Field(alias='updatedAt')
    completion: int | None = Field(default=None)
    'The completion percentage for this action'
    manual_status_reason: str | None = Field(default=None, alias='manualStatusReason')
    'Describe the reason why this action has this status'
    status: MCPGetActionsAdminActionsStatus | None = Field(default=None)
    implementation_phase: MCPGetActionsAdminActionsImplementationphase | None = Field(default=None, alias='implementationPhase')
    status_summary: MCPGetActionsAdminActionsStatussummary = Field(alias='statusSummary')
    timeliness: MCPGetActionsAdminActionsTimeliness
    color: str | None = Field(default=None)
    impact: MCPGetActionsAdminActionsImpact | None = Field(default=None)
    'The impact of this action'
    primary_org: MCPGetActionsAdminActionsPrimaryorg | None = Field(default=None, alias='primaryOrg')
    responsible_parties: list[MCPGetActionsAdminActionsResponsibleparties] = Field(alias='responsibleParties')
    categories: list[MCPGetActionsAdminActionsCategories]
    contact_persons: list[MCPGetActionsAdminActionsContactpersons] = Field(alias='contactPersons')
    "Contact persons for this action. Results may be empty or redacted for unauthenticated requests depending on the plan's public contact person settings (see PlanFeatures.publicContactPersons)."
    tasks: list[MCPGetActionsAdminActionsTasks]
    related_indicators: list[MCPGetActionsAdminActionsRelatedindicators] = Field(alias='relatedIndicators')
    links: list[MCPGetActionsAdminActionsLinks]
    status_updates: list[MCPGetActionsAdminActionsStatusupdates] = Field(alias='statusUpdates')
    related_actions: list[MCPGetActionsAdminActionsRelatedactions] = Field(alias='relatedActions')
    merged_with: MCPGetActionsAdminActionsMergedwith | None = Field(default=None, alias='mergedWith')
    'Set if this action is merged with another action'
    merged_actions: list[MCPGetActionsAdminActionsMergedactions] = Field(alias='mergedActions')
    'Set if this action is merged with another action'
    superseded_by: MCPGetActionsAdminActionsSupersededby | None = Field(default=None, alias='supersededBy')
    'Set if this action is superseded by another action'
    superseded_actions: list[MCPGetActionsAdminActionsSupersededactions] = Field(alias='supersededActions')
    'Set if this action is superseded by another action'
    all_dependency_relationships: list[MCPGetActionsAdminActionsAlldependencyrelationships] = Field(
        alias='allDependencyRelationships'
    )
    attributes: list[
        Annotated[
            MCPGetActionsAdminActionsAttributesBaseAttributeCategoryChoice
            | MCPGetActionsAdminActionsAttributesBaseAttributeChoice
            | MCPGetActionsAdminActionsAttributesBaseAttributeNumericValue
            | MCPGetActionsAdminActionsAttributesBaseAttributeRichText
            | MCPGetActionsAdminActionsAttributesBaseAttributeText,
            Field(discriminator='typename'),
        ]
        | MCPGetActionsAdminActionsAttributesBaseCatchAll
    ]
    visibility: ActionVisibility
    order: int
    view_url: str = Field(alias='viewUrl')


class MCPGetActionsAdmin(OperationModel):
    """No documentation."""

    typename: Literal['AdminQuery'] = Field(alias='__typename', default='AdminQuery')
    actions: list[MCPGetActionsAdminActions]
    'Get actions by their IDs'


class MCPGetActions(OperationModel):
    """No documentation found for this operation."""

    admin: MCPGetActionsAdmin
    'Admin query namespace'

    class Arguments(ArgumentsModel):
        """Arguments for MCPGetActions."""

        ids: list[str]
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPGetActions."""

        document = 'query MCPGetActions($ids: [ID!]!) {\n  admin {\n    actions(ids: $ids) {\n      id\n      uuid\n      identifier\n      name\n      officialName\n      leadParagraph\n      description\n      startDate\n      endDate\n      scheduleContinuous\n      dateFormat\n      updatedAt\n      completion\n      manualStatusReason\n      status {\n        id\n        identifier\n        name\n        isCompleted\n        __typename\n      }\n      implementationPhase {\n        id\n        identifier\n        name\n        __typename\n      }\n      statusSummary {\n        identifier\n        label\n        sentiment\n        isActive\n        isCompleted\n        __typename\n      }\n      timeliness {\n        identifier\n        comparison\n        days\n        __typename\n      }\n      color\n      impact {\n        id\n        identifier\n        name\n        __typename\n      }\n      primaryOrg {\n        id\n        name\n        abbreviation\n        __typename\n      }\n      responsibleParties {\n        id\n        role\n        specifier\n        organization {\n          id\n          name\n          abbreviation\n          __typename\n        }\n        __typename\n      }\n      categories {\n        id\n        identifier\n        name\n        type {\n          id\n          identifier\n          name\n          __typename\n        }\n        __typename\n      }\n      contactPersons {\n        id\n        role\n        primaryContact\n        person {\n          id\n          firstName\n          lastName\n          title\n          email\n          organization {\n            id\n            name\n            abbreviation\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      tasks {\n        id\n        name\n        state\n        dueAt\n        completedAt\n        comment\n        __typename\n      }\n      relatedIndicators {\n        id\n        effectType\n        indicatesActionProgress\n        indicator {\n          id\n          identifier\n          name\n          unit {\n            id\n            name\n            shortName\n            __typename\n          }\n          latestValue {\n            id\n            date\n            value\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      links {\n        id\n        url\n        title\n        __typename\n      }\n      statusUpdates {\n        id\n        title\n        date\n        content\n        author {\n          id\n          firstName\n          lastName\n          __typename\n        }\n        __typename\n      }\n      relatedActions {\n        id\n        identifier\n        name\n        __typename\n      }\n      mergedWith {\n        id\n        identifier\n        name\n        __typename\n      }\n      mergedActions {\n        id\n        identifier\n        name\n        __typename\n      }\n      supersededBy {\n        id\n        identifier\n        name\n        __typename\n      }\n      supersededActions {\n        id\n        identifier\n        name\n        __typename\n      }\n      allDependencyRelationships {\n        preceding {\n          id\n          identifier\n          name\n          __typename\n        }\n        dependent {\n          id\n          identifier\n          name\n          __typename\n        }\n        __typename\n      }\n      attributes {\n        __typename\n        type {\n          identifier\n          name\n          unit {\n            shortName\n            __typename\n          }\n          __typename\n        }\n        keyIdentifier\n        ... on AttributeText {\n          textValue: value\n        }\n        ... on AttributeRichText {\n          richTextValue: value\n        }\n        ... on AttributeCategoryChoice {\n          categories {\n            identifier\n            type {\n              identifier\n            }\n          }\n        }\n        ... on AttributeNumericValue {\n          numericValue: value\n        }\n        ... on AttributeChoice {\n          choice {\n            identifier\n          }\n        }\n      }\n      visibility\n      order\n      viewUrl\n      __typename\n    }\n    __typename\n  }\n}'


AttributeTypeInput.model_rebuild()
