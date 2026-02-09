# Unit Testing Guide

## Overview

Kausal Watch uses pytest with Django integration for testing. The test suite covers models, GraphQL APIs, REST APIs, permissions, and business logic. Tests are organized by Django app, with each app containing a `tests/` subdirectory.

## Test Configuration

### Running Tests

```bash
# Run all tests (includes kausal_watch_extensions if available)
python run_tests.py

# Run with pytest directly; reuse database to speed up test runs
pytest --reuse-db

# Run specific test file
pytest --reuse-db actions/tests/test_models.py

# Run specific test
pytest --reuse-db actions/tests/test_models.py::test_action_can_be_saved
```

### Pytest Configuration

Configuration is in `pyproject.toml` under `[tool.pytest.ini_options]`:

- **DJANGO_SETTINGS_MODULE**: `aplans.settings`
- **testpaths**: `**/tests` - Discovers all test files in `tests/` directories
- **Test environment**: Uses `.env.test` via `pytest-env`
- **Database**: Search index auto-update is disabled for tests

Key pytest plugins used:
- `pytest-django` - Django integration
- `pytest-factoryboy` - Factory Boy fixture registration
- `pytest-cov` - Coverage reporting
- `pytest-html` - HTML test reports

## Test File Organization

### Directory Structure

Tests are organized within each Django app:

```
actions/
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Fixtures used across multiple test files
│   ├── fixtures.py          # Complex fixture definitions
│   ├── factories.py         # Factory Boy factories
│   ├── utils.py             # Test utilities and helpers
│   ├── test_models.py       # Model tests
│   ├── test_graphql_action.py   # GraphQL API tests
│   ├── test_graphql_plan.py
│   ├── test_api.py          # Django REST Framework tests
│   └── test_*.py            # Other test modules
```

### Naming Conventions

- **Model tests**: `test_models.py`
- **GraphQL tests**: `test_graphql_*.py` (e.g., `test_graphql_action.py`, `test_graphql_plan.py`)
  - Older files may use `test_schema.py` but prefer `test_graphql_*`
- **REST API tests**: `test_api.py`
- **Other tests**: `test_<feature>.py` (e.g., `test_permissions.py`, `test_search_indexing.py`)

### Fixture Organization

- **`conftest.py`**: Fixtures expected to be widely used by multiple test files in the same directory or subdirectories
- **`fixtures.py`**: Fixtures needed by more than one test file but not as widely used as conftest fixtures
- **Within test files**: Fixtures used only by that specific test file

## Factory Boy and Test Data

### The ModelFactory Base Class

Kausal Watch uses a custom `ModelFactory[T]` base class (defined in `aplans/factories.py`) that supports generic type hints:

```python
from aplans.factories import ModelFactory
from actions.models import Action

class ActionFactory(ModelFactory[Action]):
    name = Sequence(lambda i: f"Action {i}")
    plan = SubFactory(PlanFactory)
```

No need to annotate instances returned by `.create()`:

```python
action = ActionFactory.create()  # Type checker knows this is an Action
```

### Factory Definitions

Factories are defined in `<app>/tests/factories.py`. Example from `actions/tests/factories.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING
from factory.declarations import Sequence, SubFactory
from aplans.factories import ModelFactory
from actions.models import Plan

if TYPE_CHECKING:
    from collections.abc import Callable
    from django.dispatch.dispatcher import Signal
    def mute_signals[X](signal: Signal) -> Callable[[X], X]: ...
else:
    mute_signals = factory.django.mute_signals

@mute_signals(post_save)
class PlanFactory(ModelFactory[Plan]):
    organization = SubFactory(OrganizationFactory)
    name = Sequence(lambda i: f"Plan {i}")
    identifier = Sequence(lambda i: f'plan{i}')
    primary_language = 'en'
    other_languages = ['fi']
```

**Signal muting**: Use `@mute_signals(post_save)` on factories when you want to prevent signal handlers from running during object creation. This is common for objects that trigger side effects (e.g., creating related objects, sending notifications, or Wagtail reference/search index updates).

### Factory Fixture Registration

Factories are registered as pytest fixtures in the root `conftest.py` using `pytest-factoryboy`:

```python
from pytest_factoryboy import register, LazyFixture
from actions.tests import factories as actions_factories

# Simple registration - creates fixtures with default names
register(actions_factories.ActionFactory)  # Creates 'action' fixture
register(actions_factories.PlanFactory)    # Creates 'plan' fixture

# Customized registration - creates specialized fixtures
register(
    actions_factories.AttributeTypeFactory,
    'action_attribute_type',
    name=Sequence(lambda i: f"Action attribute type {i}"),
    object_content_type=LazyAttribute(
        lambda _: ContentType.objects.get(app_label='actions', model='action')
    ),
    scope=SubFactory(actions_factories.PlanFactory),
)

# Using LazyFixture for dependencies
register(
    actions_factories.IndicatorFactory,
    plans=LazyFixture(lambda plan: [plan])
)
```

This creates:
- A bare fixture (e.g., `action`) that returns a single instance
- A factory fixture (e.g., `action_factory`) that can be called to create instances

### When to Use Factory.create() vs Fixtures

**Use bare fixtures** (`action`, `plan`) when:
- You need exactly one instance with default values
- You don't need to customize the instance
- You want to declare dependencies implicitly via fixture arguments

```python
def test_action_belongs_to_plan(plan: Plan, action: Action):
    # 'action' fixture automatically uses 'plan' fixture if configured
    assert action.plan == plan
```

**Use Factory.create()** when:
- You need to customize the instance
- You need multiple instances
- You want explicit control over creation

```python
from actions.tests.factories import ActionFactory

def test_actions_with_different_statuses():
    draft_action: Action = ActionFactory.create(visibility='draft')
    public_action: Action = ActionFactory.create(visibility='public')
    assert draft_action.visibility != public_action.visibility
```

**Use customized factory fixtures** when:
- You have a commonly-used variant across many tests
- The customization is complex and should be reusable

```python
def test_with_specialized_fixture(action_attribute_type__text: AttributeTypeFactory):
    # This fixture is registered with specific customizations
    assert action_attribute_type__text.format == AttributeType.AttributeFormat.TEXT
```

**Avoid using factory-as-function** (`action_factory()`) unless the factory has customizations in the registration. Since type hints require importing the Factory class anyway, prefer `ActionFactory.create()` for clarity and type safety.

## Type Annotations in Tests

**IMPORTANT**: Test files must include type annotations just like production code. Use Python 3.13+ type annotations:

```python
# Good
from collections.abc import Sequence

def abc(my_list: list[int]): ...

class MyGeneric[M: Model]:
    def __init__(self, obj: M): ...


# Bad
from typing import Sequence   # Deprecated; use collections.abc instead

def abc(my_list: List[int]):   # Lower-case `list` and `dict` etc. are preferred

_ModelT = TypeVar('_ModelT', bound=Model)  # Legacy syntax
```

### Required Imports

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actions.models import Action
    from users.models import User
```

### Annotating Test Functions

```python
def test_action_creation():
    # Shouldn't annotate – Factory.create() methods should already be typed.
    action = ActionFactory.create()
    assert action.name is not None

def test_with_typed_fixture(user: User):
    assert user.is_authenticated
```

### Annotating Helper Functions

```python
def create_test_hierarchy(plan: Plan, depth: int) -> list[Category]:
    categories: list[Category] = []
    for i in range(depth):
        category = CategoryFactory.create(plan=plan)
        categories.append(category)
    return categories
```

## Common Testing Patterns

### Model Tests

Mark test modules with `pytestmark = pytest.mark.django_db`:

```python
import pytest
from actions.models import Action
from actions.tests.factories import ActionFactory

pytestmark = pytest.mark.django_db


def test_action_can_be_saved():
    ActionFactory()


def test_action_query_set_modifiable_by_contact_person(action, action_contact):
    assert action in Action.objects.qs.modifiable_by(action_contact.person.user)
```

### GraphQL Tests

Use the `graphql_client_query_data` fixture (defined in root `conftest.py`) for making GraphQL queries:

```python
pytestmark = pytest.mark.django_db


QUERY = """
  query($id: ID!) {
    action(id: $id) {
      id
      name
      plan { id }
    }
  }
"""


def test_action_query(graphql_client_query_data, action):
    data = graphql_client_query_data(
        QUERY,
        variables={'id': action.id},
    )
    expected = {
        'action': {
            'id': str(action.id),
            'name': action.name,
            'plan': {'id': str(action.plan.id)},
        },
    }
    assert data == expected
```

**Note**: `graphql_client_query_data` makes a request, asserts there are no errors, and returns the `data` field. For testing error cases, use `graphql_client_query` instead.

### REST API Tests

Use the `api_client` fixture (a `JSONAPIClient` that automatically parses JSON responses):

```python
pytestmark = pytest.mark.django_db


def test_plan_list_endpoint(api_client, plan):
    url = reverse('plan-list')
    response = api_client.get(url)
    assert response.status_code == 200
    assert len(response.json_data) >= 1
```

For authenticated requests:

```python
def test_authenticated_request(api_client, user, token):
    api_client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
    response = api_client.get('/v1/protected-endpoint/')
    assert response.status_code == 200
```

### Parametrized Tests

Use `@pytest.mark.parametrize` for testing multiple scenarios:

```python
@pytest.mark.parametrize('color', ['#ffffff', '#000000', '#abc123'])
def test_category_color_valid(color):
    category = CategoryFactory()
    category.color = color
    category.full_clean()  # Should not raise


@pytest.mark.parametrize('color', ['invalid', '#fffffg', '#00'])
def test_category_color_invalid(color):
    category = CategoryFactory()
    category.color = color
    with pytest.raises(ValidationError):
        category.full_clean()
```

Parametrize fixtures by setting fixture parameters:

```python
@pytest.mark.parametrize('notification_settings__notifications_enabled', [True])
def test_with_modified_fixture(plan):
    # The 'plan' fixture's notification_settings will have notifications_enabled=True
    assert plan.notification_settings.notifications_enabled
```

### Testing Visibility and Permissions

```python
from aplans.utils import InstancesVisibleForMixin


def test_attribute_visibility_for_contact_person(plan, action, person):
    at = AttributeTypeFactory(
        object_content_type=ContentType.objects.get_for_model(Action),
        scope=plan,
        instances_visible_for=InstancesVisibleForMixin.VisibleFor.CONTACT_PERSONS,
    )
    attr = AttributeTextFactory(type=at, content_object=action)

    # Not visible to regular users
    assert not attr.is_visible_for_user(person.user, plan)

    # Make person a contact for the action
    ActionContactFactory(action=action, person=person)
    assert attr.is_visible_for_user(person.user, plan)
```

## Test Utilities

### Custom Assertion Helpers

Create reusable assertion functions in `tests/utils.py`:

```python
def assert_log_entry_created(instance: PlanRelatedModelWithRevision, action: Action, user: User, plan: Plan):
    """Assert that a PlanScopedModelLogEntry was created for a given instance."""
    content_type = ContentType.objects.get_for_model(instance, for_concrete_model=False)
    log_entry = PlanScopedModelLogEntry.objects.filter(
        content_type=content_type,
        object_id=str(instance.pk),
        action=action,
        plan=plan
    ).first()
    assert log_entry is not None, (
        f'Expected PlanScopedModelLogEntry for {instance.__class__.__name__} '
        f'id={instance.pk}, action=\'{action}\', plan={plan.pk}, but none found'
    )
    assert log_entry.user_id == user.pk
    return log_entry
```

### Tree-based Testing Helpers

For hierarchical data (like organization structures), use tree helpers:

```python
from orgs.tests.utils import assert_org_hierarchy


def test_organization_hierarchy(organization_hierarchy_factory):
    organization_hierarchy_factory("""
        1
        2
            2.1
            2.2
        3
            3.1
    """)

    # Make changes...

    assert_org_hierarchy("""
        1
        2
            2.1
        3
            2.2
            3.1
    """)
```

## Common Global Fixtures

These fixtures are available in all tests (defined in root `conftest.py`):

### Django and Auth Fixtures

- `user` - Regular user
- `superuser` - User with `is_superuser=True`
- `plan_admin_user` - User who is a plan administrator
- `action_contact_person` - Person who is a contact for an action
- `token` - DRF authentication token for `user`
- `uuid` - String UUID for `user`

### API Client Fixtures

- `client` - Django test client
- `api_client` - `JSONAPIClient` (auto-parses JSON, sets Accept header)
- `graphql_client_query` - Makes GraphQL request, returns full response
- `graphql_client_query_data` - Makes GraphQL request, asserts no errors, returns `data` field

### Error Testing Fixture

- `contains_error` - Helper for checking GraphQL error responses:

```python
def test_graphql_error(graphql_client_query, contains_error):
    response = graphql_client_query(QUERY, variables={'id': 'invalid'})
    assert contains_error(response, code='NOT_FOUND')
    assert contains_error(response, message='Action not found')
```

### Model Instance Fixtures

Most model factories are registered and available as fixtures. Common ones:

- `plan` - Plan instance
- `action` - Action instance
- `category` - Category instance
- `category_type` - CategoryType instance
- `indicator` - Indicator instance
- `organization` - Organization instance
- `person` - Person instance

Use `<model>_factory` to create additional instances:

```python
from actions.tests.factories import ActionFactory

def test_multiple_actions(action: Action):
    action2 = ActionFactory.create(plan=action.plan)  # if the new action should be in the same plan
    action3 = ActionFactory.create()
    assert action.id != action2.id != action3.id
```

## Best Practices

### 1. Always Add Type Annotations

```python
# Good
def test_action_name(action: Action):
    name = action.name  # no need to annotate `name`
    assert len(name) > 0

# Bad
def test_action_name(action):
    name = action.name
    assert len(name) > 0
```

### 2. Use Descriptive Test Names

```python
# Good
def test_action_query_set_modifiable_by_contact_person(action: Action, action_contact_person: ActionContactPerson):
    ...

# Bad
def test_action_1(action, action_contact_person):
    ...
```

### 3. Test One Concept Per Test

```python
# Good
def test_action_visibility_internal(action: Action):
    action.visibility = 'internal'
    assert not action.is_public()

def test_action_visibility_public(action: Action):
    action.visibility = 'public'
    assert action.is_public()

# Bad
def test_action_visibility(action):
    action.visibility = 'internal'
    assert not action.is_public()
    action.visibility = 'public'
    assert action.is_public()
```

### 4. Use Factories Over Manual Object Creation

```python
# Good
def test_action_with_category():
    action = ActionFactory.create()
    category = CategoryFactory.create(type__plan=action.plan)
    action.categories.add(category)

# Bad
def test_action_with_category(plan):
    action = Action.objects.create(plan=plan, name='Test')
    category_type = CategoryType.objects.create(plan=plan, name='Type')
    category = Category.objects.create(type=category_type, name='Cat')
    action.categories.add(category)
```

### 5. Prefer pytest-style Assertions

```python
# Good
def test_action_count():
    assert Action.objects.count() == 0

# Avoid (Django TestCase style)
def test_action_count():
    self.assertEqual(Action.objects.count(), 0)
```

### 6. Use `pytestmark` for Database Access

Mark test modules that need database access:

```python
import pytest

pytestmark = pytest.mark.django_db
```

For individual tests (if most tests in the module don't need DB):

```python
@pytest.mark.django_db
def test_with_database_access():
    action = ActionFactory.create()
    assert action.id is not None
```
