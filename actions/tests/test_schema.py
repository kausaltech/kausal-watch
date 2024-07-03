import pytest
from datetime import date
from decimal import Decimal

from actions.models.features import OrderBy
from actions.tests.factories import (
    ActionFactory, ActionContactFactory, ActionImpactFactory, ActionImplementationPhaseFactory,
    ActionResponsiblePartyFactory, ActionScheduleFactory, ActionStatusFactory, ActionStatusUpdateFactory,
    ActionTaskFactory, CategoryFactory, CategoryTypeFactory, ImpactGroupFactory,
    ImpactGroupActionFactory, PlanFactory, PlanDomainFactory, MonitoringQualityPointFactory, ScenarioFactory
)
from indicators.tests.factories import ActionIndicatorFactory, IndicatorFactory, IndicatorLevelFactory
from pages.tests.factories import CategoryPageFactory

from .fixtures import *

pytestmark = pytest.mark.django_db


def test_plan_domain_node(graphql_client_query_data):
    plan = PlanFactory()
    domain = PlanDomainFactory(plan=plan)
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $hostname: String!) {
          plan(id: $plan) {
            domain(hostname: $hostname) {
              id
              hostname
              googleSiteVerificationTag
              matomoAnalyticsUrl
            }
          }
        }
        ''',
        variables=dict(plan=plan.identifier, hostname=domain.hostname)
    )
    expected = {
        'plan': {
            'domain': {
                'id': str(domain.id),
                'hostname': domain.hostname,
                'googleSiteVerificationTag': domain.google_site_verification_tag,
                'matomoAnalyticsUrl': domain.matomo_analytics_url,
            },
        }
    }
    assert data == expected


def test_plan_node(graphql_client_query_data, plan_with_pages):
    plan = plan_with_pages
    domain = PlanDomainFactory(plan=plan)
    action_schedule = ActionScheduleFactory(plan=plan)
    action = ActionFactory(plan=plan, schedule=[action_schedule])
    category_type = CategoryTypeFactory(plan=plan)
    # Switch off RelatedFactory _action because it would generate an extra action
    impact_group = ImpactGroupFactory(plan=plan)
    ImpactGroupActionFactory(group=impact_group, action=action, impact=action.impact)
    monitoring_quality_point = MonitoringQualityPointFactory(plan=plan)
    indicator_level = IndicatorLevelFactory(plan=plan)
    scenario = ScenarioFactory(plan=plan)
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $hostname: String!) {
          plan(id: $plan) {
            __typename
            id
            name
            identifier
            image {
              __typename
              id
            }
            actionSchedules {
              __typename
              id
            }
            actions {
              __typename
              id
            }
            categoryTypes {
              __typename
              id
            }
            actionStatuses {
              __typename
              id
            }
            indicatorLevels {
              __typename
              id
            }
            actionImpacts {
              __typename
              id
            }
            generalContent {
              __typename
              id
            }
            impactGroups {
              __typename
              id
            }
            monitoringQualityPoints {
              __typename
              id
            }
            scenarios {
              __typename
              id
            }
            primaryLanguage
            otherLanguages
            accessibilityStatementUrl
            actionImplementationPhases {
              __typename
              id
            }
            lastActionIdentifier
            serveFileBaseUrl
            pages {
              __typename
              # TODO: Check the id field, but getting it from other pages than the root page is not trivial
            }
            domain(hostname: $hostname) {
              __typename
              id
            }
            mainMenu {
              __typename
            }
            footer {
              __typename
            }
            additionalLinks {
              __typename
            }
          }
        }
        ''',
        variables={'plan': plan.identifier, 'hostname': domain.hostname}
    )
    expected = {
        'plan': {
            '__typename': 'Plan',
            'id': plan.identifier,
            'name': plan.name,
            'identifier': plan.identifier,
            'image': {
                '__typename': 'Image',
                'id': str(plan.image.id),
            },
            'actionSchedules': [{
                '__typename': 'ActionSchedule',
                'id': str(action_schedule.id),
            }],
            'actions': [{
                '__typename': 'Action',
                'id': str(action.id),
            }],
            'categoryTypes': [{
                '__typename': 'CategoryType',
                'id': str(category_type.id),
            }],
            'actionStatuses': [{
                '__typename': 'ActionStatus',
                'id': str(action.status.id),
            }],
            'indicatorLevels': [{
                '__typename': 'IndicatorLevel',
                'id': str(indicator_level.id),
            }],
            'actionImpacts': [{
                '__typename': 'ActionImpact',
                'id': str(action.impact.id),
            }],
            'generalContent': {
                '__typename': 'SiteGeneralContent',
                'id': str(plan.general_content.id),
            },
            'impactGroups': [{
                '__typename': 'ImpactGroup',
                'id': str(impact_group.id),
            }],
            'monitoringQualityPoints': [{
                '__typename': 'MonitoringQualityPoint',
                'id': str(monitoring_quality_point.id),
            }],
            'scenarios': [{
                '__typename': 'Scenario',
                'id': str(scenario.id),
            }],
            'primaryLanguage': plan.primary_language,
            'otherLanguages': plan.other_languages,
            'accessibilityStatementUrl': plan.accessibility_statement_url,
            'actionImplementationPhases': [{
                '__typename': 'ActionImplementationPhase',
                'id': str(action.implementation_phase.id),
            }],
            'lastActionIdentifier': plan.get_last_action_identifier(),
            'serveFileBaseUrl': 'http://testserver',
            'pages': [
                {
                    '__typename': 'PlanRootPage',
                },
                {
                    '__typename': 'ActionListPage',
                },
                {
                    '__typename': 'IndicatorListPage',
                },
                {
                    '__typename': 'PrivacyPolicyPage',
                },
                {
                    '__typename': 'AccessibilityStatementPage',
                },
            ],
            'domain': {
                '__typename': 'PlanDomain',
                'id': str(plan.domains.first().id),
            },
            'mainMenu': {
                '__typename': 'MainMenu',
            },
            'footer': {
                '__typename': 'Footer',
            },
            'additionalLinks': {
                '__typename': 'AdditionalLinks',
            },
        }
    }
    assert data == expected


def test_plan_node_superseded_by(graphql_client_query_data):
    plan1 = PlanFactory()
    plan2 = PlanFactory(superseded_by=plan1)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            __typename
            id
            supersededBy {
              __typename
              id
            }
            supersededPlans {
              __typename
              id
            }
          }
        }
        ''',
        variables={'plan': plan2.identifier}
    )
    expected = {
        'plan': {
            '__typename': 'Plan',
            'id': plan2.identifier,
            'supersededBy': {
                '__typename': 'Plan',
                'id': plan1.identifier,
            },
            'supersededPlans': [],
        }
    }
    assert data == expected


@pytest.mark.parametrize('recursive', [False, True])
def test_plan_node_superseding_plans(graphql_client_query_data, recursive):
    plan1 = PlanFactory()
    plan2 = PlanFactory(superseded_by=plan1)
    plan3 = PlanFactory(superseded_by=plan2)
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $recursive: Boolean!) {
          plan(id: $plan) {
            __typename
            id
            supersedingPlans(recursive: $recursive) {
              __typename
              id
            }
          }
        }
        ''',
        variables={'plan': plan3.identifier, 'recursive': recursive}
    )
    expected_superseding_plans = [plan2]
    if recursive:
        expected_superseding_plans.append(plan1)
    expected = {
        'plan': {
            '__typename': 'Plan',
            'id': plan3.identifier,
            'supersedingPlans': [{
                '__typename': 'Plan',
                'id': plan.identifier,
            } for plan in expected_superseding_plans],
        }
    }
    assert data == expected


@pytest.mark.parametrize('recursive', [False, True])
def test_plan_node_superseded_plans(graphql_client_query_data, recursive):
    plan1 = PlanFactory()
    plan2 = PlanFactory(superseded_by=plan1)
    plan3 = PlanFactory(superseded_by=plan2)
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $recursive: Boolean!) {
          plan(id: $plan) {
            __typename
            id
            supersededBy {
              __typename
              id
            }
            supersededPlans(recursive: $recursive) {
              __typename
              id
            }
          }
        }
        ''',
        variables={'plan': plan1.identifier, 'recursive': recursive}
    )
    expected_superseded_plans = [plan2]
    if recursive:
        expected_superseded_plans.append(plan3)
    expected = {
        'plan': {
            '__typename': 'Plan',
            'id': plan1.identifier,
            'supersededBy': None,
            'supersededPlans': [{
                '__typename': 'Plan',
                'id': plan.identifier,
            } for plan in expected_superseded_plans],
        }
    }
    assert data == expected


def test_plan_actions_responsible_organization(graphql_client_query_data):
    plan = PlanFactory()
    ActionFactory(plan=plan)  # org is not responsible
    action = ActionFactory(plan=plan)
    arp = ActionResponsiblePartyFactory(action=action)
    org = arp.organization
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $org: ID!) {
          plan(id: $plan) {
            actions(responsibleOrganization: $org) {
              __typename
              id
            }
          }
        }
        ''',
        variables={'plan': plan.identifier, 'org': org.id}
    )
    expected = {
        'plan': {
            'actions': [{
                '__typename': 'Action',
                'id': str(action.id),
            }],
        }
    }
    assert data == expected


def test_attribute_choice_node(
    graphql_client_query_data, plan, attribute_choice, attribute_type__ordered_choice,
    attribute_type_choice_option
):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            attributes {
              ... on AttributeChoice {
                id
                type {
                  __typename
                }
                choice {
                  __typename
                  id
                  identifier
                  name
                }
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'attributes': [{
                'id': 'C' + str(attribute_choice.id),
                'type': {
                    '__typename': 'AttributeType',
                },
                'choice': {
                    '__typename': 'AttributeTypeChoiceOption',
                    'id': str(attribute_type_choice_option.id),
                    'identifier': attribute_type_choice_option.identifier,
                    'name': attribute_type_choice_option.name,
                },
            }]
        }]
    }
    assert data == expected


def test_attribute_text_node(
    graphql_client_query_data, plan, attribute_text, attribute_type__text
):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            attributes {
              ... on AttributeText {
                id
                type {
                  __typename
                }
                key
                keyIdentifier
                value
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'attributes': [{
                'id': str(attribute_text.id),
                'type': {
                    '__typename': 'AttributeType',
                },
                'key': attribute_type__text.name,
                'keyIdentifier': attribute_type__text.identifier,
                'value': attribute_text.text,
            }]
        }]
    }
    assert data == expected


def test_attribute_rich_text_node(
    graphql_client_query_data, plan, attribute_rich_text, attribute_type__rich_text
):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            attributes {
              ... on AttributeRichText {
                id
                type {
                  __typename
                }
                key
                keyIdentifier
                value
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'attributes': [{
                'id': str(attribute_rich_text.id),
                'type': {
                    '__typename': 'AttributeType',
                },
                'key': attribute_type__rich_text.name,
                'keyIdentifier': attribute_type__rich_text.identifier,
                'value': attribute_rich_text.text,
            }]
        }]
    }
    assert data == expected


def test_category_level_node(graphql_client_query_data, plan, category_level, category):
    # We need to include the `category` fixture so we can access the CategoryLevelNode via planCategories
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            level {
              ... on CategoryLevel {
                id
                order
                type {
                  __typename
                }
                name
                namePlural
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'level': {
                'id': str(category_level.id),
                'order': 1,
                'type': {
                    '__typename': 'CategoryType',
                },
                'name': category_level.name,
                'namePlural': category_level.name_plural,
            }
        }]
    }
    assert data == expected


def test_attribute_type_node(
    graphql_client_query_data, plan, attribute_rich_text, attribute_choice,
    attribute_type__rich_text, attribute_type__ordered_choice
):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            type {
              attributeTypes {
                identifier
                name
                helpText
                format
                unit {
                  __typename
                }
                showChoiceNames
                hasZeroOption
                choiceOptions {
                  __typename
                }
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'type': {
                'attributeTypes': [{
                    'identifier': attribute_type__rich_text.identifier,
                    'name': attribute_type__rich_text.name,
                    'helpText': attribute_type__rich_text.help_text,
                    'format': 'RICH_TEXT',
                    'unit': None,
                    'showChoiceNames': attribute_type__rich_text.show_choice_names,
                    'hasZeroOption': attribute_type__rich_text.has_zero_option,
                    'choiceOptions': [],
                }, {
                    'identifier': attribute_type__ordered_choice.identifier,
                    'name': attribute_type__ordered_choice.name,
                    'helpText': attribute_type__ordered_choice.help_text,
                    'format': 'ORDERED_CHOICE',
                    'unit': attribute_type__ordered_choice.unit,
                    'showChoiceNames': attribute_type__ordered_choice.show_choice_names,
                    'hasZeroOption': attribute_type__ordered_choice.has_zero_option,
                    'choiceOptions': [{
                        '__typename': 'AttributeTypeChoiceOption',
                    }],
                }]
            }
        }]
    }
    assert data == expected


def test_attribute_type_choice_option_node(
    graphql_client_query_data, plan, attribute_type_choice_option, attribute_choice
):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            type {
              attributeTypes {
                choiceOptions {
                  identifier
                  name
                }
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'type': {
                'attributeTypes': [{
                    'choiceOptions': [{
                        'identifier': attribute_type_choice_option.identifier,
                        'name': attribute_type_choice_option.name,
                    }],
                }]
            }
        }]
    }
    assert data == expected


# TODO: test_common_category_type_node


def test_category_type_node(
    graphql_client_query_data, plan, category_type, category, category_level, attribute_type__rich_text
):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            type {
              id
              plan {
                __typename
                # Workaround: I just want __typename, but this causes an error due to graphene-django-optimizer.
                identifier
              }
              name
              identifier
              leadParagraph
              helpText
              usableForActions
              usableForIndicators
              editableForActions
              editableForIndicators
              common {
                __typename
              }
              levels {
                __typename
              }
              categories {
                __typename
              }
              attributeTypes {
                __typename
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'type': {
                'id': str(category_type.id),
                'plan': {
                    '__typename': 'Plan',
                    'identifier': plan.identifier,
                },
                'name': category_type.name,
                'identifier': category_type.identifier,
                'leadParagraph': category_type.lead_paragraph,
                'helpText': category_type.help_text,
                'usableForActions': category_type.usable_for_actions,
                'usableForIndicators': category_type.usable_for_indicators,
                'editableForActions': category_type.editable_for_actions,
                'editableForIndicators': category_type.editable_for_indicators,
                'common': {
                    '__typename': 'CommonCategoryType'
                },
                'levels': [{
                    '__typename': 'CategoryLevel'
                }],
                'categories': [{
                    '__typename': 'Category'
                }],
                'attributeTypes': [{
                    '__typename': 'AttributeType'
                }],
            }
        }]
    }
    assert data == expected


# TODO: test_common_category_node


def test_category_node(
    graphql_client_query_data, plan_with_pages, category_type, category, category_level, attribute_rich_text,
    attribute_choice
):
    plan = plan_with_pages
    child_category = CategoryFactory(parent=category)
    CategoryPageFactory(category=category)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            id
            type {
              __typename
            }
            order
            identifier
            name
            parent {
              __typename
            }
            leadParagraph
            helpText
            color
            children {
              __typename
              id
              parent {
                __typename
                id
              }
            }
            categoryPage {
              __typename
            }
            image {
              __typename
            }
            attributes {
              __typename
            }
            level {
              __typename
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'id': str(category.id),
            'type': {
              '__typename': 'CategoryType',
            },
            'order': 1,
            'identifier': category.identifier,
            'name': category.name,
            'parent': None,
            'leadParagraph': category.lead_paragraph,
            'helpText': category.help_text,
            'color': category.color,
            'children': [{
                '__typename': 'Category',
                'id': str(child_category.id),
                'parent': {
                  '__typename': 'Category',
                  'id': str(category.id),
                }
            }],
            'categoryPage': {
                '__typename': 'CategoryPage',
            },
            'image': {
                '__typename': 'Image',
            },
            'attributes': [{
                '__typename': 'AttributeRichText',
            }, {
                '__typename': 'AttributeChoice',
            }],
            'level': {
                '__typename': 'CategoryLevel',
            },
        }]
    }
    assert data == expected


def test_scenario_node(graphql_client_query_data):
    scenario = ScenarioFactory()
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            scenarios {
              id
              plan {
                __typename
              }
              name
              identifier
              description
            }
          }
        }
        ''',
        variables={'plan': scenario.plan.identifier}
    )
    expected = {
        'plan': {
            'scenarios': [{
                'id': str(scenario.id),
                'plan': {
                    '__typename': 'Plan',
                },
                'name': scenario.name,
                'identifier': scenario.identifier,
                'description': scenario.description,
            }]
        }
    }
    assert data == expected


def test_impact_group_node(graphql_client_query_data):
    impact_group = ImpactGroupFactory()
    impact_group_action = ImpactGroupActionFactory(group=impact_group)
    impact_group_child = ImpactGroupFactory(plan=impact_group.plan, parent=impact_group)
    impact_group_action_child = ImpactGroupActionFactory(group=impact_group_child)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            impactGroups {
              id
              plan {
                __typename
                id
              }
              identifier
              parent {
                __typename
                id
              }
              weight
              color
              actions {
                __typename
                id
              }
              name
            }
          }
        }
        ''',
        variables={'plan': impact_group.plan.identifier}
    )
    expected = {
        'plan': {
            'impactGroups': [{
                'id': str(impact_group.id),
                'plan': {
                    '__typename': 'Plan',
                    'id': impact_group.plan.identifier,
                },
                'identifier': impact_group.identifier,
                'parent': None,
                'weight': impact_group.weight,
                'color': impact_group.color,
                'actions': [{
                    '__typename': 'ImpactGroupAction',
                    'id': str(impact_group_action.id),
                }],
                'name': impact_group.name,
            }, {
                'id': str(impact_group_child.id),
                'plan': {
                    '__typename': 'Plan',
                    'id': impact_group_child.plan.identifier,
                },
                'identifier': impact_group_child.identifier,
                'parent': {
                    '__typename': 'ImpactGroup',
                    'id': str(impact_group.id),
                },
                'weight': impact_group_child.weight,
                'color': impact_group_child.color,
                'actions': [{
                    '__typename': 'ImpactGroupAction',
                    'id': str(impact_group_action_child.id),
                }],
                'name': impact_group_child.name,
            }]
        }
    }
    assert data == expected


def test_impact_group_action_node(graphql_client_query_data):
    impact_group_action = ImpactGroupActionFactory()
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            impactGroups {
              actions {
                id
                group {
                  __typename
                  id
                }
                action {
                  __typename
                  id
                }
                impact {
                  __typename
                  id
                }
              }
            }
          }
        }
        ''',
        variables={'plan': impact_group_action.group.plan.identifier}
    )
    expected = {
        'plan': {
            'impactGroups': [{
                'actions': [{
                    'id': str(impact_group_action.id),
                    'group': {
                        '__typename': 'ImpactGroup',
                        'id': str(impact_group_action.group.id),
                    },
                    'action': {
                        '__typename': 'Action',
                        'id': str(impact_group_action.action.id),
                    },
                    'impact': {
                        '__typename': 'ActionImpact',
                        'id': str(impact_group_action.impact.id),
                    },
                }],
            }]
        }
    }
    assert data == expected


def test_monitoring_quality_point_node(graphql_client_query_data):
    monitoring_quality_point = MonitoringQualityPointFactory()
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            monitoringQualityPoints {
              id
              name
              descriptionYes
              descriptionNo
              plan {
                __typename
                id
              }
              identifier
            }
          }
        }
        ''',
        variables={'plan': monitoring_quality_point.plan.identifier}
    )
    expected = {
        'plan': {
            'monitoringQualityPoints': [{
                'id': str(monitoring_quality_point.id),
                'name': monitoring_quality_point.name,
                'descriptionYes': monitoring_quality_point.description_yes,
                'descriptionNo': monitoring_quality_point.description_no,
                'plan': {
                  '__typename': 'Plan',
                  'id': str(monitoring_quality_point.plan.identifier),
                },
                'identifier': monitoring_quality_point.identifier,
            }]
        }
    }
    assert data == expected


def test_action_task_node(graphql_client_query_data):
    action_task = ActionTaskFactory()
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planActions(plan: $plan) {
            tasks {
              id
              action {
                __typename
                id
              }
              name
              state
              comment
              dueAt
              completedAt
              createdAt
              modifiedAt
            }
          }
        }
        ''',
        variables={'plan': action_task.action.plan.identifier}
    )
    expected = {
        'planActions': [{
            'tasks': [{
                'id': str(action_task.id),
                'action': {
                    '__typename': 'Action',
                    'id': str(action_task.action.id),
                },
                'name': action_task.name,
                # graphene_django puts choices into upper case in converter.convert_choice_name()
                'state': action_task.state.upper(),
                'comment': action_task.comment,
                'dueAt': action_task.due_at.isoformat(),
                'completedAt': None,
                # 'completedBy': action_task.completed_by,
                'createdAt': action_task.created_at.isoformat(),
                'modifiedAt': action_task.modified_at.isoformat(),
            }]
        }]
    }
    assert data == expected


def test_action_node(graphql_client_query_data):
    plan = PlanFactory()
    action_schedule = ActionScheduleFactory(plan=plan)
    category = CategoryFactory()
    monitoring_quality_point = MonitoringQualityPointFactory()
    action = ActionFactory(plan=plan,
                           categories=[category],
                           monitoring_quality_points=[monitoring_quality_point],
                           schedule=[action_schedule])
    indicator = IndicatorFactory(organization=plan.organization)
    action_indicator = ActionIndicatorFactory(action=action, indicator=indicator)
    action_responsible_party = ActionResponsiblePartyFactory(action=action, organization=plan.organization)
    action_status_update = ActionStatusUpdateFactory(action=action)
    action_task = ActionTaskFactory(action=action)
    action_contact = ActionContactFactory(action=action, person__organization=plan.organization)
    impact_group_action = ImpactGroupActionFactory(action=action, group__plan=action.plan, impact=action.impact)
    data = graphql_client_query_data(
        '''
        query($action: ID!) {
          action(id: $action) {
            __typename
            id
            plan {
              __typename
              id
            }
            name
            officialName
            identifier
            description
            status {
              __typename
              id
            }
            completion
            schedule {
              __typename
              id
            }
            responsibleParties {
              __typename
              id
            }
            categories {
              __typename
              id
            }
            indicators {
              __typename
              id
            }
            contactPersons {
              __typename
              id
            }
            updatedAt
            tasks {
              __typename
              id
            }
            relatedIndicators {
              __typename
              id
            }
            impact {
              __typename
              id
            }
            statusUpdates {
              __typename
              id
            }
            # The following are in a separate test case
            # mergedWith {
            #   __typename
            #   id
            # }
            # mergedActions {
            #   __typename
            #   id
            # }
            impactGroups {
              __typename
              id
            }
            monitoringQualityPoints {
              __typename
              id
            }
            implementationPhase {
              __typename
              id
            }
            manualStatusReason
            # The following are in a separate test case
            # nextAction {
            #   __typename
            #   id
            # }
            # previousAction {
            #   __typename
            #   id
            # }
            image {
              __typename
              id
            }
          }
        }
        ''',
        variables={'action': action.id}
    )
    expected = {
        'action': {
            '__typename': 'Action',
            'id': str(action.id),
            'plan': {
                '__typename': 'Plan',
                'id': str(plan.identifier),
            },
            'name': action.name,
            'officialName': action.official_name,
            'identifier': action.identifier,
            'description': action.description,
            'status': {
                '__typename': 'ActionStatus',
                'id': str(action.status.id),
            },
            'completion': action.completion,
            'schedule': [{
                '__typename': 'ActionSchedule',
                'id': str(action_schedule.id),
            }],
            'responsibleParties': [{
                '__typename': 'ActionResponsibleParty',
                'id': str(action_responsible_party.id),
            }],
            'categories': [{
                '__typename': 'Category',
                'id': str(category.id),
            }],
            'indicators': [{
                '__typename': 'Indicator',
                'id': str(indicator.id),
            }],
            'contactPersons': [{
                '__typename': 'ActionContactPerson',
                'id': str(action_contact.id),
            }],
            'updatedAt': action.updated_at.isoformat(),
            'tasks': [{
                '__typename': 'ActionTask',
                'id': str(action_task.id),
            }],
            'relatedIndicators': [{
                '__typename': 'ActionIndicator',
                'id': str(action_indicator.id),
            }],
            'impact': {
                '__typename': 'ActionImpact',
                'id': str(action.impact.id),
            },
            'statusUpdates': [{
                '__typename': 'ActionStatusUpdate',
                'id': str(action_status_update.id),
            }],
            'impactGroups': [{
                '__typename': 'ImpactGroupAction',
                'id': str(impact_group_action.id),
            }],
            'monitoringQualityPoints': [{
                '__typename': 'MonitoringQualityPoint',
                'id': str(monitoring_quality_point.id),
            }],
            'implementationPhase': {
                '__typename': 'ActionImplementationPhase',
                'id': str(action.implementation_phase.id),
            },
            'manualStatusReason': action.manual_status_reason,
            'image': {
                '__typename': 'Image',
                'id': str(action.image.id),
            },
        }
    }
    assert data == expected


def test_action_node_merged(graphql_client_query_data):
    plan = PlanFactory()
    action1 = ActionFactory(plan=plan)
    action2 = ActionFactory(plan=plan, merged_with=action1)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planActions(plan: $plan) {
            __typename
            id
            mergedWith {
              __typename
              id
            }
            mergedActions {
              __typename
              id
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planActions': [{
            '__typename': 'Action',
            'id': str(action1.id),
            'mergedWith': None,
            'mergedActions': [{
                '__typename': 'Action',
                'id': str(action2.id),
            }],
        }, {
            '__typename': 'Action',
            'id': str(action2.id),
            'mergedWith': {
                '__typename': 'Action',
                'id': str(action1.id),
            },
            'mergedActions': [],
        }]
    }
    assert data == expected


def test_action_node_superseded(graphql_client_query_data):
    plan = PlanFactory()
    action1 = ActionFactory(plan=plan)
    action2 = ActionFactory(plan=plan, superseded_by=action1)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planActions(plan: $plan) {
            __typename
            id
            supersededBy {
              __typename
              id
            }
            supersededActions {
              __typename
              id
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planActions': [{
            '__typename': 'Action',
            'id': str(action1.id),
            'supersededBy': None,
            'supersededActions': [{
                '__typename': 'Action',
                'id': str(action2.id),
            }],
        }, {
            '__typename': 'Action',
            'id': str(action2.id),
            'supersededBy': {
                '__typename': 'Action',
                'id': str(action1.id),
            },
            'supersededActions': [],
        }]
    }
    assert data == expected


def test_action_node_next_previous(graphql_client_query_data):
    plan = PlanFactory()
    action1 = ActionFactory(plan=plan)
    action2 = ActionFactory(plan=plan)
    assert action1.get_next_action(None) == action2
    assert action2.get_next_action(None) is None
    assert action1.get_previous_action(None) is None
    assert action2.get_previous_action(None) == action1
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planActions(plan: $plan) {
            __typename
            id
            nextAction {
              __typename
              id
            }
            previousAction {
              __typename
              id
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planActions': [{
            '__typename': 'Action',
            'id': str(action1.id),
            'nextAction': {
                '__typename': 'Action',
                'id': str(action2.id),
            },
            'previousAction': None,
        }, {
            '__typename': 'Action',
            'id': str(action2.id),
            'nextAction': None,
            'previousAction': {
                '__typename': 'Action',
                'id': str(action1.id),
            }
        }]
    }
    assert data == expected

@pytest.mark.parametrize('ordering',
  [
    OrderBy.NONE,
    OrderBy.NAME    
  ])
def test_action_node_related_indicators_ordering(graphql_client_query_data, ordering):
    plan = PlanFactory()
    action = ActionFactory(plan=plan)
    indicator1 = IndicatorFactory(name="c", organization=plan.organization)
    indicator2 = IndicatorFactory(name="a", organization=plan.organization)
    indicator3 = IndicatorFactory(name="b", organization=plan.organization)
    action_indicator1 = ActionIndicatorFactory(action=action, indicator=indicator1)
    action_indicator2 = ActionIndicatorFactory(action=action, indicator=indicator2)
    action_indicator3 = ActionIndicatorFactory(action=action, indicator=indicator3)
    plan.features.indicator_ordering = ordering
    plan.features.save()
    data = graphql_client_query_data(
        '''
        query($action: ID!) {
          action(id: $action) {
            __typename
            id
            relatedIndicators {
              __typename
              id
            }
          }
        }
        ''',
        variables={'action': action.id}
    )
    expected = {
        'action': {
              '__typename': 'Action',
              'id': str(action.id),
        }
    }
    if ordering == OrderBy.NONE:
      expected["action"]["relatedIndicators"] = [{
                  '__typename': 'ActionIndicator',
                  'id': str(action_indicator3.id),
                },
                {
                  '__typename': 'ActionIndicator',
                  'id': str(action_indicator2.id),
                },
                {
                    '__typename': 'ActionIndicator',
                    'id': str(action_indicator1.id),
                }]
    elif ordering == OrderBy.NAME:
        expected["action"]["relatedIndicators"] = [{
                  '__typename': 'ActionIndicator',
                  'id': str(action_indicator2.id),
                },
                {
                  '__typename': 'ActionIndicator',
                  'id': str(action_indicator3.id),
                },
                {
                    '__typename': 'ActionIndicator',
                    'id': str(action_indicator1.id),
                }]

    assert data == expected


def test_action_schedule_node(graphql_client_query_data):
    plan = PlanFactory()
    action_schedule = ActionScheduleFactory(plan=plan)
    action = ActionFactory(plan=plan, schedule=[action_schedule])
    data = graphql_client_query_data(
        '''
        query($action: ID!) {
          action(id: $action) {
            schedule {
              __typename
              id
              plan {
                __typename
                id
              }
              beginsAt
              endsAt
            }
          }
        }
        ''',
        variables={'action': action.id}
    )
    expected = {
        'action': {
            'schedule': [{
                '__typename': 'ActionSchedule',
                'id': str(action_schedule.id),
                'plan': {
                   '__typename': 'Plan',
                   'id': plan.identifier,
                },
                'beginsAt': action_schedule.begins_at.isoformat(),
                'endsAt': action_schedule.ends_at.isoformat(),
            }]
        }
    }
    assert data == expected


def test_action_status_node(graphql_client_query_data):
    plan = PlanFactory()
    action_status = ActionStatusFactory(plan=plan)
    action = ActionFactory(plan=plan, status=action_status)
    data = graphql_client_query_data(
        '''
        query($action: ID!) {
          action(id: $action) {
            status {
              __typename
              id
              plan {
                __typename
                id
              }
              name
              identifier
              isCompleted
            }
          }
        }
        ''',
        variables={'action': action.id}
    )
    expected = {
        'action': {
            'status': {
                '__typename': 'ActionStatus',
                'id': str(action_status.id),
                'plan': {
                   '__typename': 'Plan',
                   'id': plan.identifier,
                },
                'name': action_status.name,
                'identifier': action_status.identifier,
                'isCompleted': action_status.is_completed,
            }
        }
    }
    assert data == expected


def test_action_implementation_phase_node(graphql_client_query_data):
    plan = PlanFactory()
    action_implementation_phase = ActionImplementationPhaseFactory(plan=plan)
    action = ActionFactory(plan=plan, implementation_phase=action_implementation_phase)
    data = graphql_client_query_data(
        '''
        query($action: ID!) {
          action(id: $action) {
            implementationPhase {
              __typename
              id
              plan {
                __typename
                id
              }
              order
              name
              identifier
            }
          }
        }
        ''',
        variables={'action': action.id}
    )
    expected = {
        'action': {
            'implementationPhase': {
                '__typename': 'ActionImplementationPhase',
                'id': str(action_implementation_phase.id),
                'plan': {
                   '__typename': 'Plan',
                   'id': plan.identifier,
                },
                'order': action_implementation_phase.order,
                'name': action_implementation_phase.name,
                'identifier': action_implementation_phase.identifier,
            }
        }
    }
    assert data == expected


def test_action_responsible_party_node(graphql_client_query_data):
    plan = PlanFactory()
    action = ActionFactory(plan=plan)
    action_responsible_party = ActionResponsiblePartyFactory(action=action, organization=plan.organization)
    data = graphql_client_query_data(
        '''
        query($action: ID!) {
          action(id: $action) {
            responsibleParties {
              __typename
              id
              action {
                __typename
                id
              }
              organization {
                __typename
                id
              }
              role
              specifier
              order
            }
          }
        }
        ''',
        variables={'action': action.id}
    )
    expected = {
        'action': {
            'responsibleParties': [{
                '__typename': 'ActionResponsibleParty',
                'id': str(action_responsible_party.id),
                'action': {
                   '__typename': 'Action',
                   'id': str(action.id),
                },
                'organization': {
                   '__typename': 'Organization',
                   'id': str(plan.organization.id),
                },
                'role': action_responsible_party.role.upper(),
                'specifier': action_responsible_party.specifier,
                'order': action_responsible_party.order,
            }]
        }
    }
    assert data == expected


def test_action_contact_person_node(graphql_client_query_data):
    plan = PlanFactory()
    action = ActionFactory(plan=plan)
    action_contact = ActionContactFactory(action=action, person__organization=plan.organization)
    data = graphql_client_query_data(
        '''
        query($action: ID!) {
          action(id: $action) {
            contactPersons {
              __typename
              id
              action {
                __typename
                id
              }
              person {
                __typename
                id
              }
              order
              primaryContact
            }
          }
        }
        ''',
        variables={'action': action.id}
    )
    expected = {
        'action': {
            'contactPersons': [{
                '__typename': 'ActionContactPerson',
                'id': str(action_contact.id),
                'action': {
                   '__typename': 'Action',
                   'id': str(action.id),
                },
                'person': {
                   '__typename': 'Person',
                   'id': str(action_contact.person.id),
                },
                'order': action_contact.order,
                'primaryContact': action_contact.primary_contact,
            }]
        }
    }
    assert data == expected


def test_action_impact_node(graphql_client_query_data):
    plan = PlanFactory()
    action_impact = ActionImpactFactory(plan=plan)
    action = ActionFactory(plan=plan, impact=action_impact)
    data = graphql_client_query_data(
        '''
        query($action: ID!) {
          action(id: $action) {
            impact {
              __typename
              id
              plan {
                __typename
                id
              }
              name
              identifier
              order
            }
          }
        }
        ''',
        variables={'action': action.id}
    )
    expected = {
        'action': {
            'impact': {
                '__typename': 'ActionImpact',
                'id': str(action_impact.id),
                'plan': {
                   '__typename': 'Plan',
                   'id': plan.identifier,
                },
                'name': action_impact.name,
                'identifier': action_impact.identifier,
                'order': action_impact.order,
            }
        }
    }
    assert data == expected


def test_action_status_update_node(graphql_client_query_data):
    action = ActionFactory()
    action_status_update = ActionStatusUpdateFactory(action=action)
    data = graphql_client_query_data(
        '''
        query($action: ID!) {
          action(id: $action) {
            statusUpdates {
              __typename
              id
              action {
                __typename
                id
              }
              title
              date
              author {
                __typename
                id
              }
              content
            }
          }
        }
        ''',
        variables={'action': action.id}
    )
    expected = {
        'action': {
            'statusUpdates': [{
                '__typename': 'ActionStatusUpdate',
                'id': str(action_status_update.id),
                'action': {
                   '__typename': 'Action',
                   'id': str(action.id),
                },
                'title': action_status_update.title,
                'date': action_status_update.date.isoformat(),
                'author': {
                    '__typename': 'Person',
                    'id': str(action_status_update.author.id),
                },
                'content': action_status_update.content,
            }]
        }
    }
    assert data == expected
