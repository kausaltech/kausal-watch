from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from mcp_server.generated_base import ArgumentsModel, InputTypeModel, MutationModel, ObjectBaseModel, QueryModel


class ActionContactPersonRole(StrEnum):
    """An enumeration."""

    EDITOR = 'EDITOR'
    'Editor'
    MODERATOR = 'MODERATOR'
    'Moderator'


class ActionDateFormat(StrEnum):
    """An enumeration."""

    FULL = 'FULL'
    'Day, month and year (31.12.2020)'
    MONTH_YEAR = 'MONTH_YEAR'
    'Month and year (12.2020)'
    YEAR = 'YEAR'
    'Year (2020)'


class ActionIndicatorEffectType(StrEnum):
    """An enumeration."""

    INCREASES = 'INCREASES'
    'increases'
    DECREASES = 'DECREASES'
    'decreases'


class ActionResponsiblePartyRole(StrEnum):
    """An enumeration."""

    NONE = 'NONE'
    'Unspecified'
    PRIMARY = 'PRIMARY'
    'Primary responsible party'
    COLLABORATOR = 'COLLABORATOR'
    'Collaborator'


class ActionStatusSummaryIdentifier(StrEnum):
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


class ActionTaskState(StrEnum):
    """An enumeration."""

    NOT_STARTED = 'NOT_STARTED'
    'not started'
    IN_PROGRESS = 'IN_PROGRESS'
    'in progress'
    COMPLETED = 'COMPLETED'
    'completed'
    CANCELLED = 'CANCELLED'
    'cancelled'


class ActionTimelinessIdentifier(StrEnum):
    """An enumeration."""

    OPTIMAL = 'OPTIMAL'
    ACCEPTABLE = 'ACCEPTABLE'
    LATE = 'LATE'
    STALE = 'STALE'


class ActionVisibility(StrEnum):
    """An enumeration."""

    INTERNAL = 'INTERNAL'
    'Internal'
    PUBLIC = 'PUBLIC'
    'Public'


class AttributeTypeFormat(StrEnum):
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


class CategoryTypeSelectWidget(StrEnum):
    """An enumeration."""

    SINGLE = 'SINGLE'
    'Single'
    MULTIPLE = 'MULTIPLE'
    'Multiple'


class Comparison(StrEnum):
    """An enumeration."""

    LTE = 'LTE'
    GT = 'GT'


class OperationMessageKind(StrEnum):
    """No documentation."""

    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    PERMISSION = 'PERMISSION'
    VALIDATION = 'VALIDATION'


class PlanFeaturesContactPersonsPublicData(StrEnum):
    """An enumeration."""

    NONE = 'NONE'
    'Do not show contact persons publicly'
    NAME = 'NAME'
    'Show only name, role and affiliation'
    ALL = 'ALL'
    'Show all information'
    ALL_FOR_AUTHENTICATED = 'ALL_FOR_AUTHENTICATED'
    'Show all information but only for authenticated users'


class Sentiment(StrEnum):
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
    'The PK or identifier of the plan'
    organization_id: str = Field(alias='organizationId')
    'The PK of the organization'


class AttributeTypeInput(InputTypeModel):
    """AttributeType(id, latest_revision, order, instances_editable_by, instances_visible_for, primary_language_lowercase, object_content_type, scope_content_type, scope_id, name, identifier, help_text, format, unit, attribute_category_type, show_choice_names, has_zero_option, max_length, show_in_reporting_tab, primary_language, other_languages, i18n)."""

    plan_id: str = Field(alias='planId')
    identifier: str
    name: str
    format: AttributeTypeFormat
    'The format of the attributes with this type'
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
    select_widget: CategoryTypeSelectWidget | None = Field(alias='selectWidget', default=None)
    'Choose "Multiple" only if more than one category can be selected at a time, otherwise choose "Single" which is the default.'
    usable_for_actions: bool | None = Field(alias='usableForActions', default=None)
    usable_for_indicators: bool | None = Field(alias='usableForIndicators', default=None)
    synchronize_with_pages: bool | None = Field(alias='synchronizeWithPages', default=None)
    'Should a content page hierarchy be automatically generated for the categories. If not set, defaults to the value of `primaryActionClassification`.'
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
    'The official name of the organization'
    abbreviation: str | None = None
    'Short abbreviation (e.g. "NASA", "YM")'
    parent_id: str | None = Field(alias='parentId', default=None)
    'ID of the parent organization; omit for a root organization'
    primary_language: str = Field(alias='primaryLanguage')
    'Primary language code (ISO 639-1, e.g. "en-US", "fi", "de-CH").'


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
    short_name: str | None = Field(alias='shortName', default=None)
    'A shorter version of the plan name'
    country: str
    'ISO 3166-1 country code (e.g. FI, DE, US)'
    primary_language: str = Field(alias='primaryLanguage')
    'Primary language code (ISO 639-1, e.g. "en-US", "fi", "de-CH")'
    other_languages: list[str] = Field(alias='otherLanguages')
    'Additional language codes (ISO 639-1)'
    theme_identifier: str | None = Field(alias='themeIdentifier', default=None)
    features: PlanFeaturesInput | None = None


class OpInfoMessages(ObjectBaseModel):
    """No documentation."""

    typename: Literal['OperationMessage'] = Field(alias='__typename', default='OperationMessage')
    kind: OperationMessageKind
    'The kind of this message.'
    message: str
    'The error message.'
    field: str | None = Field(default=None)
    "The field that caused the error, or `null` if it isn't associated with any particular field."
    code: str | None = Field(default=None)
    'The error code, or `null` if no error code was set.'


class OpInfo(ObjectBaseModel):
    """No documentation."""

    typename: Literal['OperationInfo'] = Field(alias='__typename', default='OperationInfo')
    messages: list[OpInfoMessages]
    'List of messages returned by the operation.'

    class Meta:
        """Meta class for OpInfo."""

        document = 'fragment OpInfo on OperationInfo {\n  messages {\n    kind\n    message\n    field\n    code\n    __typename\n  }\n  __typename\n}'
        name = 'OpInfo'
        type = 'OperationInfo'


class PlanConciseOrganization(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'


class PlanConcise(ObjectBaseModel):
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
    organization: PlanConciseOrganization
    'The main organization for the plan'

    class Meta:
        """Meta class for PlanConcise."""

        document = 'fragment PlanConcise on Plan {\n  id\n  identifier\n  name\n  shortName\n  versionName\n  primaryLanguage\n  otherLanguages\n  publishedAt\n  viewUrl\n  organization {\n    id\n    name\n    __typename\n  }\n  __typename\n}'
        name = 'PlanConcise'
        type = 'Plan'


class PlanDetailsFeatures(ObjectBaseModel):
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


class PlanDetailsCategorytypes(ObjectBaseModel):
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


class PlanDetailsActionstatussummaries(ObjectBaseModel):
    """No documentation."""

    typename: Literal['ActionStatusSummary'] = Field(alias='__typename', default='ActionStatusSummary')
    identifier: ActionStatusSummaryIdentifier
    label: str
    is_active: bool = Field(alias='isActive')
    is_completed: bool = Field(alias='isCompleted')
    sentiment: Sentiment


class PlanDetailsActionattributetypesUnit(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Unit'] = Field(alias='__typename', default='Unit')
    id: str
    short_name: str | None = Field(default=None, alias='shortName')


class PlanDetailsActionattributetypesChoiceoptions(ObjectBaseModel):
    """No documentation."""

    typename: Literal['AttributeTypeChoiceOption'] = Field(alias='__typename', default='AttributeTypeChoiceOption')
    id: str
    identifier: str
    name: str


class PlanDetailsActionattributetypes(ObjectBaseModel):
    """No documentation."""

    typename: Literal['AttributeType'] = Field(alias='__typename', default='AttributeType')
    id: str
    identifier: str
    name: str
    format: AttributeTypeFormat
    unit: PlanDetailsActionattributetypesUnit | None = Field(default=None)
    choice_options: list[PlanDetailsActionattributetypesChoiceoptions] = Field(alias='choiceOptions')


class PlanDetails(ObjectBaseModel):
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
    features: PlanDetailsFeatures
    category_types: list[PlanDetailsCategorytypes] = Field(alias='categoryTypes')
    action_status_summaries: list[PlanDetailsActionstatussummaries] = Field(alias='actionStatusSummaries')
    action_attribute_types: list[PlanDetailsActionattributetypes] = Field(alias='actionAttributeTypes')

    class Meta:
        """Meta class for PlanDetails."""

        document = 'fragment PlanDetails on Plan {\n  id\n  identifier\n  name\n  shortName\n  versionName\n  primaryLanguage\n  otherLanguages\n  publishedAt\n  viewUrl\n  accessibilityStatementUrl\n  externalFeedbackUrl\n  features {\n    publicContactPersons\n    hasActionIdentifiers\n    hasActionOfficialName\n    hasActionLeadParagraph\n    hasActionPrimaryOrgs\n    enableSearch\n    enableIndicatorComparison\n    minimalStatuses\n    contactPersonsPublicData\n    __typename\n  }\n  categoryTypes {\n    id\n    identifier\n    name\n    usableForActions\n    usableForIndicators\n    __typename\n  }\n  actionStatusSummaries {\n    identifier\n    label\n    isActive\n    isCompleted\n    sentiment\n    __typename\n  }\n  actionAttributeTypes {\n    id\n    identifier\n    name\n    format\n    unit {\n      id\n      shortName\n      __typename\n    }\n    choiceOptions {\n      id\n      identifier\n      name\n      __typename\n    }\n    __typename\n  }\n  __typename\n}'
        name = 'PlanDetails'
        type = 'Plan'


class OrganizationBriefParent(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str


class OrganizationBrief(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'
    abbreviation: str | None = Field(default=None)
    'Short version or abbreviation of the organization name to be displayed when it is not necessary to show the full name'
    parent: OrganizationBriefParent | None = Field(default=None)

    class Meta:
        """Meta class for OrganizationBrief."""

        document = 'fragment OrganizationBrief on Organization {\n  id\n  name\n  abbreviation\n  parent {\n    id\n    __typename\n  }\n  __typename\n}'
        name = 'OrganizationBrief'
        type = 'Organization'


class CategoryLevelDetails(ObjectBaseModel):
    """
    Hierarchy level within a CategoryType.

    Root level has order=0, first child level order=1 and so on.
    """

    typename: Literal['CategoryLevel'] = Field(alias='__typename', default='CategoryLevel')
    id: str
    name: str
    name_plural: str | None = Field(default=None, alias='namePlural')
    order: int

    class Meta:
        """Meta class for CategoryLevelDetails."""

        document = 'fragment CategoryLevelDetails on CategoryLevel {\n  id\n  name\n  namePlural\n  order\n  __typename\n}'
        name = 'CategoryLevelDetails'
        type = 'CategoryLevel'


class CategoryDetailsParent(ObjectBaseModel):
    """A category for actions and indicators."""

    typename: Literal['Category'] = Field(alias='__typename', default='Category')
    id: str


class CategoryDetails(ObjectBaseModel):
    """A category for actions and indicators."""

    typename: Literal['Category'] = Field(alias='__typename', default='Category')
    id: str
    identifier: str
    name: str
    parent: CategoryDetailsParent | None = Field(default=None)
    order: int

    class Meta:
        """Meta class for CategoryDetails."""

        document = 'fragment CategoryDetails on Category {\n  id\n  identifier\n  name\n  parent {\n    id\n    __typename\n  }\n  order\n  __typename\n}'
        name = 'CategoryDetails'
        type = 'Category'


class AttributeTypeDetailsUnit(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Unit'] = Field(alias='__typename', default='Unit')
    id: str
    short_name: str | None = Field(default=None, alias='shortName')


class AttributeTypeDetailsChoiceoptions(ObjectBaseModel):
    """No documentation."""

    typename: Literal['AttributeTypeChoiceOption'] = Field(alias='__typename', default='AttributeTypeChoiceOption')
    id: str
    identifier: str
    name: str


class AttributeTypeDetails(ObjectBaseModel):
    """No documentation."""

    typename: Literal['AttributeType'] = Field(alias='__typename', default='AttributeType')
    id: str
    identifier: str
    name: str
    format: AttributeTypeFormat
    help_text: str = Field(alias='helpText')
    unit: AttributeTypeDetailsUnit | None = Field(default=None)
    choice_options: list[AttributeTypeDetailsChoiceoptions] = Field(alias='choiceOptions')

    class Meta:
        """Meta class for AttributeTypeDetails."""

        document = 'fragment AttributeTypeDetails on AttributeType {\n  id\n  identifier\n  name\n  format\n  helpText\n  unit {\n    id\n    shortName\n    __typename\n  }\n  choiceOptions {\n    id\n    identifier\n    name\n    __typename\n  }\n  __typename\n}'
        name = 'AttributeTypeDetails'
        type = 'AttributeType'


class ActionDetailsStatus(ObjectBaseModel):
    """The current status for the action ("on time", "late", "completed", etc.)."""

    typename: Literal['ActionStatus'] = Field(alias='__typename', default='ActionStatus')
    id: str
    identifier: str
    name: str
    is_completed: bool = Field(alias='isCompleted')


class ActionDetailsImplementationphase(ObjectBaseModel):
    """No documentation."""

    typename: Literal['ActionImplementationPhase'] = Field(alias='__typename', default='ActionImplementationPhase')
    id: str
    identifier: str
    name: str


class ActionDetailsStatussummary(ObjectBaseModel):
    """No documentation."""

    typename: Literal['ActionStatusSummary'] = Field(alias='__typename', default='ActionStatusSummary')
    identifier: ActionStatusSummaryIdentifier
    label: str
    sentiment: Sentiment
    is_active: bool = Field(alias='isActive')
    is_completed: bool = Field(alias='isCompleted')


class ActionDetailsTimeliness(ObjectBaseModel):
    """No documentation."""

    typename: Literal['ActionTimeliness'] = Field(alias='__typename', default='ActionTimeliness')
    identifier: ActionTimelinessIdentifier
    comparison: Comparison
    days: int


class ActionDetailsImpact(ObjectBaseModel):
    """An impact classification for an action in an action plan."""

    typename: Literal['ActionImpact'] = Field(alias='__typename', default='ActionImpact')
    id: str
    identifier: str
    name: str


class ActionDetailsPrimaryorg(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'
    abbreviation: str | None = Field(default=None)
    'Short version or abbreviation of the organization name to be displayed when it is not necessary to show the full name'


class ActionDetailsResponsiblepartiesOrganization(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'
    abbreviation: str | None = Field(default=None)
    'Short version or abbreviation of the organization name to be displayed when it is not necessary to show the full name'


class ActionDetailsResponsibleparties(ObjectBaseModel):
    """No documentation."""

    typename: Literal['ActionResponsibleParty'] = Field(alias='__typename', default='ActionResponsibleParty')
    id: str
    role: ActionResponsiblePartyRole | None = Field(default=None)
    specifier: str
    'The responsibility domain for the organization'
    organization: ActionDetailsResponsiblepartiesOrganization


class ActionDetailsCategoriesType(ObjectBaseModel):
    """
    Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    typename: Literal['CategoryType'] = Field(alias='__typename', default='CategoryType')
    id: str
    identifier: str
    name: str


class ActionDetailsCategories(ObjectBaseModel):
    """A category for actions and indicators."""

    typename: Literal['Category'] = Field(alias='__typename', default='Category')
    id: str
    identifier: str
    name: str
    type: ActionDetailsCategoriesType


class ActionDetailsContactpersonsPersonOrganization(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Organization'] = Field(alias='__typename', default='Organization')
    id: str
    name: str
    'Full name of the organization'
    abbreviation: str | None = Field(default=None)
    'Short version or abbreviation of the organization name to be displayed when it is not necessary to show the full name'


class ActionDetailsContactpersonsPerson(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Person'] = Field(alias='__typename', default='Person')
    id: str
    first_name: str = Field(alias='firstName')
    last_name: str = Field(alias='lastName')
    title: str | None = Field(default=None)
    'Job title or role of this person'
    email: str
    organization: ActionDetailsContactpersonsPersonOrganization


class ActionDetailsContactpersons(ObjectBaseModel):
    """A Person acting as a contact for an action."""

    typename: Literal['ActionContactPerson'] = Field(alias='__typename', default='ActionContactPerson')
    id: str
    role: ActionContactPersonRole
    primary_contact: bool = Field(alias='primaryContact')
    'Is this person the primary contact person for the action?'
    person: ActionDetailsContactpersonsPerson


class ActionDetailsTasks(ObjectBaseModel):
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


class ActionDetailsRelatedindicatorsIndicatorUnit(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Unit'] = Field(alias='__typename', default='Unit')
    id: str
    name: str
    short_name: str | None = Field(default=None, alias='shortName')


class ActionDetailsRelatedindicatorsIndicatorLatestvalue(ObjectBaseModel):
    """One measurement of an indicator for a certain date/month/year."""

    typename: Literal['IndicatorValue'] = Field(alias='__typename', default='IndicatorValue')
    id: str
    date: str | None = Field(default=None)
    value: float


class ActionDetailsRelatedindicatorsIndicator(ObjectBaseModel):
    """An indicator with which to measure actions and progress towards strategic goals."""

    typename: Literal['Indicator'] = Field(alias='__typename', default='Indicator')
    id: str
    identifier: str | None = Field(default=None)
    name: str
    unit: ActionDetailsRelatedindicatorsIndicatorUnit
    latest_value: ActionDetailsRelatedindicatorsIndicatorLatestvalue | None = Field(default=None, alias='latestValue')


class ActionDetailsRelatedindicators(ObjectBaseModel):
    """Link between an action and an indicator."""

    typename: Literal['ActionIndicator'] = Field(alias='__typename', default='ActionIndicator')
    id: str
    effect_type: ActionIndicatorEffectType = Field(alias='effectType')
    'What type of effect should the action cause?'
    indicates_action_progress: bool = Field(alias='indicatesActionProgress')
    'Set if the indicator should be used to determine action progress'
    indicator: ActionDetailsRelatedindicatorsIndicator


class ActionDetailsLinks(ObjectBaseModel):
    """A link related to an action."""

    typename: Literal['ActionLink'] = Field(alias='__typename', default='ActionLink')
    id: str
    url: str
    title: str


class ActionDetailsStatusupdatesAuthor(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Person'] = Field(alias='__typename', default='Person')
    id: str
    first_name: str = Field(alias='firstName')
    last_name: str = Field(alias='lastName')


class ActionDetailsStatusupdates(ObjectBaseModel):
    """No documentation."""

    typename: Literal['ActionStatusUpdate'] = Field(alias='__typename', default='ActionStatusUpdate')
    id: str
    title: str
    date: str
    content: str
    author: ActionDetailsStatusupdatesAuthor | None = Field(default=None)


class ActionDetailsRelatedactions(ObjectBaseModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class ActionDetailsMergedwith(ObjectBaseModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class ActionDetailsMergedactions(ObjectBaseModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class ActionDetailsSupersededby(ObjectBaseModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class ActionDetailsSupersededactions(ObjectBaseModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class ActionDetailsAlldependencyrelationshipsPreceding(ObjectBaseModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class ActionDetailsAlldependencyrelationshipsDependent(ObjectBaseModel):
    """One action/measure tracked in an action plan."""

    typename: Literal['Action'] = Field(alias='__typename', default='Action')
    id: str
    identifier: str
    'The identifier for this action (e.g. number)'
    name: str


class ActionDetailsAlldependencyrelationships(ObjectBaseModel):
    """No documentation."""

    typename: Literal['ActionDependencyRelationship'] = Field(alias='__typename', default='ActionDependencyRelationship')
    preceding: ActionDetailsAlldependencyrelationshipsPreceding
    dependent: ActionDetailsAlldependencyrelationshipsDependent


class ActionDetailsAttributesTypeUnit(ObjectBaseModel):
    """No documentation."""

    typename: Literal['Unit'] = Field(alias='__typename', default='Unit')
    short_name: str | None = Field(default=None, alias='shortName')


class ActionDetailsAttributesType(ObjectBaseModel):
    """No documentation."""

    typename: Literal['AttributeType'] = Field(alias='__typename', default='AttributeType')
    identifier: str
    name: str
    unit: ActionDetailsAttributesTypeUnit | None = Field(default=None)


class ActionDetailsAttributesCategoriesType(ObjectBaseModel):
    """
    Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    typename: Literal['CategoryType'] = Field(alias='__typename', default='CategoryType')
    identifier: str


class ActionDetailsAttributesCategories(ObjectBaseModel):
    """A category for actions and indicators."""

    typename: Literal['Category'] = Field(alias='__typename', default='Category')
    identifier: str
    type: ActionDetailsAttributesCategoriesType


class ActionDetailsAttributesChoice(ObjectBaseModel):
    """No documentation."""

    typename: Literal['AttributeTypeChoiceOption'] = Field(alias='__typename', default='AttributeTypeChoiceOption')
    identifier: str


class ActionDetailsAttributesBase(ObjectBaseModel):
    """No documentation."""

    type: ActionDetailsAttributesType
    key_identifier: str = Field(alias='keyIdentifier')


class ActionDetailsAttributesBaseAttributeCategoryChoice(ActionDetailsAttributesBase, ObjectBaseModel):
    """No documentation."""

    typename: Literal['AttributeCategoryChoice'] = Field(alias='__typename', default='AttributeCategoryChoice')
    categories: list[ActionDetailsAttributesCategories]


class ActionDetailsAttributesBaseAttributeChoice(ActionDetailsAttributesBase, ObjectBaseModel):
    """No documentation."""

    typename: Literal['AttributeChoice'] = Field(alias='__typename', default='AttributeChoice')
    choice: ActionDetailsAttributesChoice | None = Field(default=None)


class ActionDetailsAttributesBaseAttributeNumericValue(ActionDetailsAttributesBase, ObjectBaseModel):
    """No documentation."""

    typename: Literal['AttributeNumericValue'] = Field(alias='__typename', default='AttributeNumericValue')
    numeric_value: float = Field(alias='numericValue')


class ActionDetailsAttributesBaseAttributeRichText(ActionDetailsAttributesBase, ObjectBaseModel):
    """No documentation."""

    typename: Literal['AttributeRichText'] = Field(alias='__typename', default='AttributeRichText')
    rich_text_value: str = Field(alias='richTextValue')


class ActionDetailsAttributesBaseAttributeText(ActionDetailsAttributesBase, ObjectBaseModel):
    """No documentation."""

    typename: Literal['AttributeText'] = Field(alias='__typename', default='AttributeText')
    text_value: str = Field(alias='textValue')


class ActionDetailsAttributesBaseCatchAll(ActionDetailsAttributesBase, ObjectBaseModel):
    """Catch all class for ActionDetailsAttributesBase."""

    typename: str = Field(alias='__typename')


class ActionDetails(ObjectBaseModel):
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
    status: ActionDetailsStatus | None = Field(default=None)
    implementation_phase: ActionDetailsImplementationphase | None = Field(default=None, alias='implementationPhase')
    status_summary: ActionDetailsStatussummary = Field(alias='statusSummary')
    timeliness: ActionDetailsTimeliness
    color: str | None = Field(default=None)
    impact: ActionDetailsImpact | None = Field(default=None)
    'The impact of this action'
    primary_org: ActionDetailsPrimaryorg | None = Field(default=None, alias='primaryOrg')
    responsible_parties: list[ActionDetailsResponsibleparties] = Field(alias='responsibleParties')
    categories: list[ActionDetailsCategories]
    contact_persons: list[ActionDetailsContactpersons] = Field(alias='contactPersons')
    "Contact persons for this action. Results may be empty or redacted for unauthenticated requests depending on the plan's public contact person settings (see PlanFeatures.publicContactPersons)."
    tasks: list[ActionDetailsTasks]
    related_indicators: list[ActionDetailsRelatedindicators] = Field(alias='relatedIndicators')
    links: list[ActionDetailsLinks]
    status_updates: list[ActionDetailsStatusupdates] = Field(alias='statusUpdates')
    related_actions: list[ActionDetailsRelatedactions] = Field(alias='relatedActions')
    merged_with: ActionDetailsMergedwith | None = Field(default=None, alias='mergedWith')
    'Set if this action is merged with another action'
    merged_actions: list[ActionDetailsMergedactions] = Field(alias='mergedActions')
    'Set if this action is merged with another action'
    superseded_by: ActionDetailsSupersededby | None = Field(default=None, alias='supersededBy')
    'Set if this action is superseded by another action'
    superseded_actions: list[ActionDetailsSupersededactions] = Field(alias='supersededActions')
    'Set if this action is superseded by another action'
    all_dependency_relationships: list[ActionDetailsAlldependencyrelationships] = Field(alias='allDependencyRelationships')
    attributes: list[
        Annotated[
            ActionDetailsAttributesBaseAttributeCategoryChoice
            | ActionDetailsAttributesBaseAttributeChoice
            | ActionDetailsAttributesBaseAttributeNumericValue
            | ActionDetailsAttributesBaseAttributeRichText
            | ActionDetailsAttributesBaseAttributeText,
            Field(discriminator='typename'),
        ]
        | ActionDetailsAttributesBaseCatchAll
    ]
    visibility: ActionVisibility
    order: int
    view_url: str = Field(alias='viewUrl')

    class Meta:
        """Meta class for ActionDetails."""

        document = 'fragment ActionDetails on Action {\n  id\n  uuid\n  identifier\n  name\n  officialName\n  leadParagraph\n  description\n  startDate\n  endDate\n  scheduleContinuous\n  dateFormat\n  updatedAt\n  completion\n  manualStatusReason\n  status {\n    id\n    identifier\n    name\n    isCompleted\n    __typename\n  }\n  implementationPhase {\n    id\n    identifier\n    name\n    __typename\n  }\n  statusSummary {\n    identifier\n    label\n    sentiment\n    isActive\n    isCompleted\n    __typename\n  }\n  timeliness {\n    identifier\n    comparison\n    days\n    __typename\n  }\n  color\n  impact {\n    id\n    identifier\n    name\n    __typename\n  }\n  primaryOrg {\n    id\n    name\n    abbreviation\n    __typename\n  }\n  responsibleParties {\n    id\n    role\n    specifier\n    organization {\n      id\n      name\n      abbreviation\n      __typename\n    }\n    __typename\n  }\n  categories {\n    id\n    identifier\n    name\n    type {\n      id\n      identifier\n      name\n      __typename\n    }\n    __typename\n  }\n  contactPersons {\n    id\n    role\n    primaryContact\n    person {\n      id\n      firstName\n      lastName\n      title\n      email\n      organization {\n        id\n        name\n        abbreviation\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  tasks {\n    id\n    name\n    state\n    dueAt\n    completedAt\n    comment\n    __typename\n  }\n  relatedIndicators {\n    id\n    effectType\n    indicatesActionProgress\n    indicator {\n      id\n      identifier\n      name\n      unit {\n        id\n        name\n        shortName\n        __typename\n      }\n      latestValue {\n        id\n        date\n        value\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  links {\n    id\n    url\n    title\n    __typename\n  }\n  statusUpdates {\n    id\n    title\n    date\n    content\n    author {\n      id\n      firstName\n      lastName\n      __typename\n    }\n    __typename\n  }\n  relatedActions {\n    id\n    identifier\n    name\n    __typename\n  }\n  mergedWith {\n    id\n    identifier\n    name\n    __typename\n  }\n  mergedActions {\n    id\n    identifier\n    name\n    __typename\n  }\n  supersededBy {\n    id\n    identifier\n    name\n    __typename\n  }\n  supersededActions {\n    id\n    identifier\n    name\n    __typename\n  }\n  allDependencyRelationships {\n    preceding {\n      id\n      identifier\n      name\n      __typename\n    }\n    dependent {\n      id\n      identifier\n      name\n      __typename\n    }\n    __typename\n  }\n  attributes {\n    __typename\n    type {\n      identifier\n      name\n      unit {\n        shortName\n        __typename\n      }\n      __typename\n    }\n    keyIdentifier\n    ... on AttributeText {\n      textValue: value\n    }\n    ... on AttributeRichText {\n      richTextValue: value\n    }\n    ... on AttributeCategoryChoice {\n      categories {\n        identifier\n        type {\n          identifier\n        }\n      }\n    }\n    ... on AttributeNumericValue {\n      numericValue: value\n    }\n    ... on AttributeChoice {\n      choice {\n        identifier\n      }\n    }\n  }\n  visibility\n  order\n  viewUrl\n  __typename\n}'
        name = 'ActionDetails'
        type = 'Action'


class CategoryTypeDetails(ObjectBaseModel):
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
    selection_type: CategoryTypeSelectWidget = Field(alias='selectionType')
    'Choose "Multiple" only if more than one category can be selected at a time, otherwise choose "Single" which is the default.'
    hide_category_identifiers: bool = Field(alias='hideCategoryIdentifiers')
    'Set if the categories do not have meaningful identifiers'
    editable_for_actions: bool = Field(alias='editableForActions')
    editable_for_indicators: bool = Field(alias='editableForIndicators')
    attribute_types: list[AttributeTypeDetails] = Field(alias='attributeTypes')
    categories: list[CategoryDetails]
    levels: list[CategoryLevelDetails]
    lead_paragraph: str | None = Field(default=None, alias='leadParagraph')
    help_text: str = Field(alias='helpText')

    class Meta:
        """Meta class for CategoryTypeDetails."""

        document = 'fragment AttributeTypeDetails on AttributeType {\n  id\n  identifier\n  name\n  format\n  helpText\n  unit {\n    id\n    shortName\n    __typename\n  }\n  choiceOptions {\n    id\n    identifier\n    name\n    __typename\n  }\n  __typename\n}\n\nfragment CategoryDetails on Category {\n  id\n  identifier\n  name\n  parent {\n    id\n    __typename\n  }\n  order\n  __typename\n}\n\nfragment CategoryLevelDetails on CategoryLevel {\n  id\n  name\n  namePlural\n  order\n  __typename\n}\n\nfragment CategoryTypeDetails on CategoryType {\n  id\n  identifier\n  name\n  usableForActions\n  usableForIndicators\n  selectionType\n  hideCategoryIdentifiers\n  editableForActions\n  editableForIndicators\n  attributeTypes {\n    ...AttributeTypeDetails\n    __typename\n  }\n  categories {\n    ...CategoryDetails\n    __typename\n  }\n  levels {\n    ...CategoryLevelDetails\n    __typename\n  }\n  leadParagraph\n  helpText\n  __typename\n}'
        name = 'CategoryTypeDetails'
        type = 'CategoryType'


class UserDetailsMe(ObjectBaseModel):
    """A user of the system."""

    typename: Literal['User'] = Field(alias='__typename', default='User')
    id: str
    uuid: str
    email: str
    first_name: str = Field(alias='firstName')
    last_name: str = Field(alias='lastName')
    is_superuser: bool = Field(alias='isSuperuser')
    'Designates that this user has all permissions without explicitly assigning them.'


class UserDetails(QueryModel):
    """No documentation found for this operation."""

    me: UserDetailsMe | None = Field(default=None)
    'The current user'

    class Arguments(ArgumentsModel):
        """Arguments for MCPUserDetails."""

        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPUserDetails."""

        document = 'query MCPUserDetails {\n  me {\n    id\n    uuid\n    email\n    firstName\n    lastName\n    isSuperuser\n    __typename\n  }\n}'


class ListPlans(QueryModel):
    """No documentation found for this operation."""

    plans: list[PlanConcise] | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPListPlans."""

        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPListPlans."""

        document = 'fragment PlanConcise on Plan {\n  id\n  identifier\n  name\n  shortName\n  versionName\n  primaryLanguage\n  otherLanguages\n  publishedAt\n  viewUrl\n  organization {\n    id\n    name\n    __typename\n  }\n  __typename\n}\n\nquery MCPListPlans {\n  plans {\n    ...PlanConcise\n    __typename\n  }\n}'


class ListActionsPlanactionsStatus(ObjectBaseModel):
    """The current status for the action ("on time", "late", "completed", etc.)."""

    typename: Literal['ActionStatus'] = Field(alias='__typename', default='ActionStatus')
    id: str
    identifier: str
    name: str
    is_completed: bool = Field(alias='isCompleted')


class ListActionsPlanactionsImplementationphase(ObjectBaseModel):
    """No documentation."""

    typename: Literal['ActionImplementationPhase'] = Field(alias='__typename', default='ActionImplementationPhase')
    id: str
    identifier: str
    name: str


class ListActionsPlanactionsStatussummary(ObjectBaseModel):
    """No documentation."""

    typename: Literal['ActionStatusSummary'] = Field(alias='__typename', default='ActionStatusSummary')
    identifier: ActionStatusSummaryIdentifier
    label: str
    sentiment: Sentiment
    is_active: bool = Field(alias='isActive')
    is_completed: bool = Field(alias='isCompleted')


class ListActionsPlanactionsResponsibleparties(ObjectBaseModel):
    """No documentation."""

    typename: Literal['ActionResponsibleParty'] = Field(alias='__typename', default='ActionResponsibleParty')
    id: str
    organization: OrganizationBrief


class ListActionsPlanactionsCategoriesType(ObjectBaseModel):
    """
    Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    typename: Literal['CategoryType'] = Field(alias='__typename', default='CategoryType')
    id: str
    identifier: str
    name: str


class ListActionsPlanactionsCategories(ObjectBaseModel):
    """A category for actions and indicators."""

    typename: Literal['Category'] = Field(alias='__typename', default='Category')
    id: str
    identifier: str
    name: str
    type: ListActionsPlanactionsCategoriesType


class ListActionsPlanactions(ObjectBaseModel):
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
    status: ListActionsPlanactionsStatus | None = Field(default=None)
    implementation_phase: ListActionsPlanactionsImplementationphase | None = Field(default=None, alias='implementationPhase')
    status_summary: ListActionsPlanactionsStatussummary = Field(alias='statusSummary')
    responsible_parties: list[ListActionsPlanactionsResponsibleparties] = Field(alias='responsibleParties')
    primary_org: OrganizationBrief | None = Field(default=None, alias='primaryOrg')
    categories: list[ListActionsPlanactionsCategories]


class ListActions(QueryModel):
    """No documentation found for this operation."""

    plan_actions: list[ListActionsPlanactions] | None = Field(default=None, alias='planActions')

    class Arguments(ArgumentsModel):
        """Arguments for MCPListActions."""

        plan: str
        category: str | None = Field(default=None)
        first: int | None = Field(default=None)
        order_by: str | None = Field(alias='orderBy', default=None)
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPListActions."""

        document = 'fragment OrganizationBrief on Organization {\n  id\n  name\n  abbreviation\n  parent {\n    id\n    __typename\n  }\n  __typename\n}\n\nquery MCPListActions($plan: ID!, $category: ID, $first: Int, $orderBy: String) @context(input: {identifier: $plan}) {\n  planActions(plan: $plan, category: $category, first: $first, orderBy: $orderBy) {\n    id\n    identifier\n    name\n    officialName\n    completion\n    scheduleContinuous\n    startDate\n    endDate\n    updatedAt\n    status {\n      id\n      identifier\n      name\n      isCompleted\n      __typename\n    }\n    implementationPhase {\n      id\n      identifier\n      name\n      __typename\n    }\n    statusSummary {\n      identifier\n      label\n      sentiment\n      isActive\n      isCompleted\n      __typename\n    }\n    responsibleParties {\n      id\n      organization {\n        ...OrganizationBrief\n        __typename\n      }\n      __typename\n    }\n    primaryOrg {\n      ...OrganizationBrief\n      __typename\n    }\n    categories {\n      id\n      identifier\n      name\n      type {\n        id\n        identifier\n        name\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}'


class GetPlan(QueryModel):
    """No documentation found for this operation."""

    plan: PlanDetails | None = Field(default=None)

    class Arguments(ArgumentsModel):
        """Arguments for MCPGetPlan."""

        identifier: str
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPGetPlan."""

        document = 'fragment PlanDetails on Plan {\n  id\n  identifier\n  name\n  shortName\n  versionName\n  primaryLanguage\n  otherLanguages\n  publishedAt\n  viewUrl\n  accessibilityStatementUrl\n  externalFeedbackUrl\n  features {\n    publicContactPersons\n    hasActionIdentifiers\n    hasActionOfficialName\n    hasActionLeadParagraph\n    hasActionPrimaryOrgs\n    enableSearch\n    enableIndicatorComparison\n    minimalStatuses\n    contactPersonsPublicData\n    __typename\n  }\n  categoryTypes {\n    id\n    identifier\n    name\n    usableForActions\n    usableForIndicators\n    __typename\n  }\n  actionStatusSummaries {\n    identifier\n    label\n    isActive\n    isCompleted\n    sentiment\n    __typename\n  }\n  actionAttributeTypes {\n    id\n    identifier\n    name\n    format\n    unit {\n      id\n      shortName\n      __typename\n    }\n    choiceOptions {\n      id\n      identifier\n      name\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nquery MCPGetPlan($identifier: ID!) @context(input: {identifier: $identifier}) {\n  plan(id: $identifier) {\n    ...PlanDetails\n    __typename\n  }\n}'


class ListOrganizationsAdmin(ObjectBaseModel):
    """No documentation."""

    typename: Literal['AdminQuery'] = Field(alias='__typename', default='AdminQuery')
    organizations: list[OrganizationBrief]
    'List of all organizations'


class ListOrganizations(QueryModel):
    """No documentation found for this operation."""

    admin: ListOrganizationsAdmin
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

        document = 'fragment OrganizationBrief on Organization {\n  id\n  name\n  abbreviation\n  parent {\n    id\n    __typename\n  }\n  __typename\n}\n\nquery MCPListOrganizations($plan: ID, $parent: ID, $depth: Int, $contains: String) {\n  admin {\n    organizations(plan: $plan, parent: $parent, depth: $depth, contains: $contains) {\n      ...OrganizationBrief\n      __typename\n    }\n    __typename\n  }\n}'


class CreateOrganizationOrganization(ObjectBaseModel):
    """No documentation."""

    typename: Literal['OrganizationMutations'] = Field(alias='__typename', default='OrganizationMutations')
    create_organization: OrganizationBrief = Field(alias='createOrganization')
    'Create a new organization'


class CreateOrganization(MutationModel):
    """No documentation found for this operation."""

    organization: CreateOrganizationOrganization

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreateOrganization."""

        input: OrganizationInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreateOrganization."""

        document = 'fragment OrganizationBrief on Organization {\n  id\n  name\n  abbreviation\n  parent {\n    id\n    __typename\n  }\n  __typename\n}\n\nmutation MCPCreateOrganization($input: OrganizationInput!) {\n  organization {\n    createOrganization(input: $input) {\n      ...OrganizationBrief\n      __typename\n    }\n    __typename\n  }\n}'


class CreatePlanPlan(ObjectBaseModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    create_plan: PlanDetails | OpInfo = Field(alias='createPlan')
    'Create a new plan; returns the newly created plan'


class CreatePlan(MutationModel):
    """No documentation found for this operation."""

    plan: CreatePlanPlan

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreatePlan."""

        input: PlanInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreatePlan."""

        document = 'fragment OpInfo on OperationInfo {\n  messages {\n    kind\n    message\n    field\n    code\n    __typename\n  }\n  __typename\n}\n\nfragment PlanDetails on Plan {\n  id\n  identifier\n  name\n  shortName\n  versionName\n  primaryLanguage\n  otherLanguages\n  publishedAt\n  viewUrl\n  accessibilityStatementUrl\n  externalFeedbackUrl\n  features {\n    publicContactPersons\n    hasActionIdentifiers\n    hasActionOfficialName\n    hasActionLeadParagraph\n    hasActionPrimaryOrgs\n    enableSearch\n    enableIndicatorComparison\n    minimalStatuses\n    contactPersonsPublicData\n    __typename\n  }\n  categoryTypes {\n    id\n    identifier\n    name\n    usableForActions\n    usableForIndicators\n    __typename\n  }\n  actionStatusSummaries {\n    identifier\n    label\n    isActive\n    isCompleted\n    sentiment\n    __typename\n  }\n  actionAttributeTypes {\n    id\n    identifier\n    name\n    format\n    unit {\n      id\n      shortName\n      __typename\n    }\n    choiceOptions {\n      id\n      identifier\n      name\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nmutation MCPCreatePlan($input: PlanInput!) {\n  plan {\n    createPlan(input: $input) {\n      ...PlanDetails\n      ...OpInfo\n      __typename\n    }\n    __typename\n  }\n}'


class AddRelatedOrganizationPlan(ObjectBaseModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    add_related_organization: PlanConcise | OpInfo = Field(alias='addRelatedOrganization')
    'Add a related organization to a plan'


class AddRelatedOrganization(MutationModel):
    """No documentation found for this operation."""

    plan: AddRelatedOrganizationPlan

    class Arguments(ArgumentsModel):
        """Arguments for MCPAddRelatedOrganization."""

        input: AddRelatedOrganizationInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPAddRelatedOrganization."""

        document = 'fragment OpInfo on OperationInfo {\n  messages {\n    kind\n    message\n    field\n    code\n    __typename\n  }\n  __typename\n}\n\nfragment PlanConcise on Plan {\n  id\n  identifier\n  name\n  shortName\n  versionName\n  primaryLanguage\n  otherLanguages\n  publishedAt\n  viewUrl\n  organization {\n    id\n    name\n    __typename\n  }\n  __typename\n}\n\nmutation MCPAddRelatedOrganization($input: AddRelatedOrganizationInput!) {\n  plan {\n    addRelatedOrganization(input: $input) {\n      ...PlanConcise\n      ...OpInfo\n      __typename\n    }\n    __typename\n  }\n}'


class DeletePlanPlan(ObjectBaseModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    delete_plan: OpInfo | None = Field(default=None, alias='deletePlan')
    'Delete a recently created plan (must be < 2 days old)'


class DeletePlan(MutationModel):
    """No documentation found for this operation."""

    plan: DeletePlanPlan

    class Arguments(ArgumentsModel):
        """Arguments for MCPDeletePlan."""

        id: str
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPDeletePlan."""

        document = 'fragment OpInfo on OperationInfo {\n  messages {\n    kind\n    message\n    field\n    code\n    __typename\n  }\n  __typename\n}\n\nmutation MCPDeletePlan($id: ID!) {\n  plan {\n    deletePlan(id: $id) {\n      ...OpInfo\n      __typename\n    }\n    __typename\n  }\n}'


class CreateActionAction(ObjectBaseModel):
    """No documentation."""

    typename: Literal['ActionMutations'] = Field(alias='__typename', default='ActionMutations')
    create_action: ActionDetails | OpInfo = Field(alias='createAction')


class CreateAction(MutationModel):
    """No documentation found for this operation."""

    action: CreateActionAction

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreateAction."""

        input: ActionInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreateAction."""

        document = 'fragment ActionDetails on Action {\n  id\n  uuid\n  identifier\n  name\n  officialName\n  leadParagraph\n  description\n  startDate\n  endDate\n  scheduleContinuous\n  dateFormat\n  updatedAt\n  completion\n  manualStatusReason\n  status {\n    id\n    identifier\n    name\n    isCompleted\n    __typename\n  }\n  implementationPhase {\n    id\n    identifier\n    name\n    __typename\n  }\n  statusSummary {\n    identifier\n    label\n    sentiment\n    isActive\n    isCompleted\n    __typename\n  }\n  timeliness {\n    identifier\n    comparison\n    days\n    __typename\n  }\n  color\n  impact {\n    id\n    identifier\n    name\n    __typename\n  }\n  primaryOrg {\n    id\n    name\n    abbreviation\n    __typename\n  }\n  responsibleParties {\n    id\n    role\n    specifier\n    organization {\n      id\n      name\n      abbreviation\n      __typename\n    }\n    __typename\n  }\n  categories {\n    id\n    identifier\n    name\n    type {\n      id\n      identifier\n      name\n      __typename\n    }\n    __typename\n  }\n  contactPersons {\n    id\n    role\n    primaryContact\n    person {\n      id\n      firstName\n      lastName\n      title\n      email\n      organization {\n        id\n        name\n        abbreviation\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  tasks {\n    id\n    name\n    state\n    dueAt\n    completedAt\n    comment\n    __typename\n  }\n  relatedIndicators {\n    id\n    effectType\n    indicatesActionProgress\n    indicator {\n      id\n      identifier\n      name\n      unit {\n        id\n        name\n        shortName\n        __typename\n      }\n      latestValue {\n        id\n        date\n        value\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  links {\n    id\n    url\n    title\n    __typename\n  }\n  statusUpdates {\n    id\n    title\n    date\n    content\n    author {\n      id\n      firstName\n      lastName\n      __typename\n    }\n    __typename\n  }\n  relatedActions {\n    id\n    identifier\n    name\n    __typename\n  }\n  mergedWith {\n    id\n    identifier\n    name\n    __typename\n  }\n  mergedActions {\n    id\n    identifier\n    name\n    __typename\n  }\n  supersededBy {\n    id\n    identifier\n    name\n    __typename\n  }\n  supersededActions {\n    id\n    identifier\n    name\n    __typename\n  }\n  allDependencyRelationships {\n    preceding {\n      id\n      identifier\n      name\n      __typename\n    }\n    dependent {\n      id\n      identifier\n      name\n      __typename\n    }\n    __typename\n  }\n  attributes {\n    __typename\n    type {\n      identifier\n      name\n      unit {\n        shortName\n        __typename\n      }\n      __typename\n    }\n    keyIdentifier\n    ... on AttributeText {\n      textValue: value\n    }\n    ... on AttributeRichText {\n      richTextValue: value\n    }\n    ... on AttributeCategoryChoice {\n      categories {\n        identifier\n        type {\n          identifier\n        }\n      }\n    }\n    ... on AttributeNumericValue {\n      numericValue: value\n    }\n    ... on AttributeChoice {\n      choice {\n        identifier\n      }\n    }\n  }\n  visibility\n  order\n  viewUrl\n  __typename\n}\n\nfragment OpInfo on OperationInfo {\n  messages {\n    kind\n    message\n    field\n    code\n    __typename\n  }\n  __typename\n}\n\nmutation MCPCreateAction($input: ActionInput!) {\n  action {\n    createAction(input: $input) {\n      ...ActionDetails\n      ...OpInfo\n      __typename\n    }\n    __typename\n  }\n}'


class CreateCategoryTypePlan(ObjectBaseModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    create_category_type: CategoryTypeDetails | OpInfo = Field(alias='createCategoryType')
    'Create a new category type; returns the newly created category type'


class CreateCategoryType(MutationModel):
    """No documentation found for this operation."""

    plan: CreateCategoryTypePlan

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreateCategoryType."""

        input: CategoryTypeInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreateCategoryType."""

        document = 'fragment AttributeTypeDetails on AttributeType {\n  id\n  identifier\n  name\n  format\n  helpText\n  unit {\n    id\n    shortName\n    __typename\n  }\n  choiceOptions {\n    id\n    identifier\n    name\n    __typename\n  }\n  __typename\n}\n\nfragment CategoryDetails on Category {\n  id\n  identifier\n  name\n  parent {\n    id\n    __typename\n  }\n  order\n  __typename\n}\n\nfragment CategoryLevelDetails on CategoryLevel {\n  id\n  name\n  namePlural\n  order\n  __typename\n}\n\nfragment CategoryTypeDetails on CategoryType {\n  id\n  identifier\n  name\n  usableForActions\n  usableForIndicators\n  selectionType\n  hideCategoryIdentifiers\n  editableForActions\n  editableForIndicators\n  attributeTypes {\n    ...AttributeTypeDetails\n    __typename\n  }\n  categories {\n    ...CategoryDetails\n    __typename\n  }\n  levels {\n    ...CategoryLevelDetails\n    __typename\n  }\n  leadParagraph\n  helpText\n  __typename\n}\n\nfragment OpInfo on OperationInfo {\n  messages {\n    kind\n    message\n    field\n    code\n    __typename\n  }\n  __typename\n}\n\nmutation MCPCreateCategoryType($input: CategoryTypeInput!) {\n  plan {\n    createCategoryType(input: $input) {\n      ...CategoryTypeDetails\n      ...OpInfo\n      __typename\n    }\n    __typename\n  }\n}'


class CreateCategoryPlan(ObjectBaseModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    create_category: CategoryDetails | OpInfo = Field(alias='createCategory')
    'Create a new category; returns the newly created category'


class CreateCategory(MutationModel):
    """No documentation found for this operation."""

    plan: CreateCategoryPlan

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreateCategory."""

        input: CategoryInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreateCategory."""

        document = 'fragment CategoryDetails on Category {\n  id\n  identifier\n  name\n  parent {\n    id\n    __typename\n  }\n  order\n  __typename\n}\n\nfragment OpInfo on OperationInfo {\n  messages {\n    kind\n    message\n    field\n    code\n    __typename\n  }\n  __typename\n}\n\nmutation MCPCreateCategory($input: CategoryInput!) {\n  plan {\n    createCategory(input: $input) {\n      ...CategoryDetails\n      ...OpInfo\n      __typename\n    }\n    __typename\n  }\n}'


class CreateAttributeTypePlan(ObjectBaseModel):
    """No documentation."""

    typename: Literal['PlanMutations'] = Field(alias='__typename', default='PlanMutations')
    create_attribute_type: AttributeTypeDetails | OpInfo = Field(alias='createAttributeType')


class CreateAttributeType(MutationModel):
    """No documentation found for this operation."""

    plan: CreateAttributeTypePlan

    class Arguments(ArgumentsModel):
        """Arguments for MCPCreateAttributeType."""

        input: AttributeTypeInput
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPCreateAttributeType."""

        document = 'fragment AttributeTypeDetails on AttributeType {\n  id\n  identifier\n  name\n  format\n  helpText\n  unit {\n    id\n    shortName\n    __typename\n  }\n  choiceOptions {\n    id\n    identifier\n    name\n    __typename\n  }\n  __typename\n}\n\nfragment OpInfo on OperationInfo {\n  messages {\n    kind\n    message\n    field\n    code\n    __typename\n  }\n  __typename\n}\n\nmutation MCPCreateAttributeType($input: AttributeTypeInput!) {\n  plan {\n    createAttributeType(input: $input) {\n      ...AttributeTypeDetails\n      ...OpInfo\n      __typename\n    }\n    __typename\n  }\n}'


class GetActionsAdmin(ObjectBaseModel):
    """No documentation."""

    typename: Literal['AdminQuery'] = Field(alias='__typename', default='AdminQuery')
    actions: list[ActionDetails]
    'Get actions by their IDs'


class GetActions(QueryModel):
    """No documentation found for this operation."""

    admin: GetActionsAdmin
    'Admin query namespace'

    class Arguments(ArgumentsModel):
        """Arguments for MCPGetActions."""

        ids: list[str]
        model_config = ConfigDict(populate_by_name=True)

    class Meta:
        """Meta class for MCPGetActions."""

        document = 'fragment ActionDetails on Action {\n  id\n  uuid\n  identifier\n  name\n  officialName\n  leadParagraph\n  description\n  startDate\n  endDate\n  scheduleContinuous\n  dateFormat\n  updatedAt\n  completion\n  manualStatusReason\n  status {\n    id\n    identifier\n    name\n    isCompleted\n    __typename\n  }\n  implementationPhase {\n    id\n    identifier\n    name\n    __typename\n  }\n  statusSummary {\n    identifier\n    label\n    sentiment\n    isActive\n    isCompleted\n    __typename\n  }\n  timeliness {\n    identifier\n    comparison\n    days\n    __typename\n  }\n  color\n  impact {\n    id\n    identifier\n    name\n    __typename\n  }\n  primaryOrg {\n    id\n    name\n    abbreviation\n    __typename\n  }\n  responsibleParties {\n    id\n    role\n    specifier\n    organization {\n      id\n      name\n      abbreviation\n      __typename\n    }\n    __typename\n  }\n  categories {\n    id\n    identifier\n    name\n    type {\n      id\n      identifier\n      name\n      __typename\n    }\n    __typename\n  }\n  contactPersons {\n    id\n    role\n    primaryContact\n    person {\n      id\n      firstName\n      lastName\n      title\n      email\n      organization {\n        id\n        name\n        abbreviation\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  tasks {\n    id\n    name\n    state\n    dueAt\n    completedAt\n    comment\n    __typename\n  }\n  relatedIndicators {\n    id\n    effectType\n    indicatesActionProgress\n    indicator {\n      id\n      identifier\n      name\n      unit {\n        id\n        name\n        shortName\n        __typename\n      }\n      latestValue {\n        id\n        date\n        value\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  links {\n    id\n    url\n    title\n    __typename\n  }\n  statusUpdates {\n    id\n    title\n    date\n    content\n    author {\n      id\n      firstName\n      lastName\n      __typename\n    }\n    __typename\n  }\n  relatedActions {\n    id\n    identifier\n    name\n    __typename\n  }\n  mergedWith {\n    id\n    identifier\n    name\n    __typename\n  }\n  mergedActions {\n    id\n    identifier\n    name\n    __typename\n  }\n  supersededBy {\n    id\n    identifier\n    name\n    __typename\n  }\n  supersededActions {\n    id\n    identifier\n    name\n    __typename\n  }\n  allDependencyRelationships {\n    preceding {\n      id\n      identifier\n      name\n      __typename\n    }\n    dependent {\n      id\n      identifier\n      name\n      __typename\n    }\n    __typename\n  }\n  attributes {\n    __typename\n    type {\n      identifier\n      name\n      unit {\n        shortName\n        __typename\n      }\n      __typename\n    }\n    keyIdentifier\n    ... on AttributeText {\n      textValue: value\n    }\n    ... on AttributeRichText {\n      richTextValue: value\n    }\n    ... on AttributeCategoryChoice {\n      categories {\n        identifier\n        type {\n          identifier\n        }\n      }\n    }\n    ... on AttributeNumericValue {\n      numericValue: value\n    }\n    ... on AttributeChoice {\n      choice {\n        identifier\n      }\n    }\n  }\n  visibility\n  order\n  viewUrl\n  __typename\n}\n\nquery MCPGetActions($ids: [ID!]!) {\n  admin {\n    actions(ids: $ids) {\n      ...ActionDetails\n      __typename\n    }\n    __typename\n  }\n}'


AttributeTypeInput.model_rebuild()
