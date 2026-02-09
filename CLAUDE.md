# CLAUDE.md

## Product Overview

Kausal Watch is an open-source platform (AGPLv3) for managing and communicating climate action plan implementation in cities and regional authorities. It replaces traditional spreadsheet-based action plan management with a structured data platform.

**Key capabilities:**
- **Action plan management** - Hierarchical organization of climate actions (themes → strategies → actions) with flexible metadata, progress tracking, and task/milestone management
- **Multi-tenancy** - Support for multiple action plans per organization, or shared regional platforms across multiple municipalities
- **Indicator tracking** - Measurable indicators linked to actions, with causal relationship visualization
- **Organization integration** - SSO via Azure AD, mirrored org structure, automatic update reminders to action owners
- **Public UI** - Customizable citizen-facing website with dashboards, filtering by department/theme, and real-time progress visualization
- **Content management** - Wagtail CMS for publishing supplementary information about action plans

**Users:**
- Climate coordinators (plan administrators)
- Department employees (action contact persons who update progress)
- Politicians and decision-makers (dashboard consumers)
- Citizens (public UI readers)

Can integrate with Kausal Paths (scenario modeling product) for emissions impact assessment.

## Development Commands

### Core Django Commands
- `python manage.py runserver` - Start development server
- `python manage.py migrate` - Run database migrations
- `python manage.py shell_plus` - Enhanced Django shell (from django-extensions)

### Testing
- `python run_tests.py` - Run all tests (includes kausal_watch_extensions if available)
- `pytest` - Alternative test runner with configuration in pyproject.toml
- Always run these commands with the flag `--reuse-db`

### Linting and Type Checking
- `ruff check` - Run code linting (configuration extends kausal_common/configs/ruff.toml)
- `mypy . | mypy-baseline filter` - Run type checking with Django plugin and baseline support

## Architecture Overview

### Core Technologies
- **Django 6.0** with Wagtail CMS for content management
- **GraphQL** APIs using both Graphene and Strawberry GraphQL
- **PostgreSQL** with PostGIS for geographic data
- **Redis** for caching and Celery task queue
- **Elasticsearch** for search functionality

### Key Django Apps Structure
- `actions/` - Core action plan management (actions, categories, plans)
- `aplans/` - Main Django project settings and shared utilities
- `indicators/` - Performance indicators and metrics
- `orgs/` - Organization management
- `people/` - Person and user management
- `pages/` - Wagtail CMS pages and content blocks
- `reports/` - Report generation and export functionality
- `notifications/` - Email notification system using MJML templates
- `admin_site/` - Custom admin interface extensions
- `kausal_common/` - git submodule for code that is shared between Kausal Paths and Kausal Watch
- `mcp_server/` - MCP server for AI assistant integration (see [architecture docs](docs/architecture/mcp-server.md))

### GraphQL Schema Architecture
The application provides dual GraphQL implementations:
- **Graphene Django** (legacy) - Located in various `schema.py` files
- **Strawberry GraphQL** (modern) - Gradually replacing Graphene
- Main schema entry: `aplans/schema.py`
- Execution context: `aplans/schema_context.py` with `WatchGraphQLContext`

### Django App File Conventions
Each Django app follows consistent naming conventions for different functionality:

- `schema.py` - GraphQL schema definitions (Graphene/Strawberry)
- `graphql_admin_schema.py` - Strawberry GraphQL types and queries requiring authentication (e.g., admin-only queries)
- `mutations.py` - Strawberry GraphQL mutations
- `api.py` - Django REST Framework components (serializers, viewsets, permissions)
- `wagtail_admin.py` - Wagtail admin interface customizations (ModelViewSet, SnippetViewSet)
  - For large admin modules, split into `*_admin.py` files (e.g., `action_admin.py`, `category_admin.py`)
- `tasks.py` - Celery task definitions for background processing
- `models.py` - Django model definitions (may be split into subdirectory for large apps)
- `apps.py` - Django app configuration
- `signals.py` - Django signal handlers
- `permissions.py` - Custom permission classes
- `utils.py` - Utility functions specific to the app

### Model Conventions
- All Django models should include a type annotation for the default manager: `objects: ClassVar[models.Manager[Self]]`.
- For ForeignKeys that point to strings, you need to add a `FK[TargetModel]` (or `FK[TargetModel | None])` type annotation to the field. Import it in a `TYPE_CHECKING` block: `from kausal_common.models.types import FK`.
- Models inheriting from `UserModifiableModel` get automatic creation/modification timestamps and user tracking

### Logging Conventions
- Use loguru for logging instead of Python's built-in logging module
- Initialize module-level logger with:
  ```python
  from loguru import logger
  logger = logger.bind(name='app.module')
  ```
- Use descriptive logger names following the pattern `app.module` (e.g., `webhooks.tasks`, `actions.models`)

### Error Handling Conventions
- Use Sentry for error reporting and monitoring
- Report exceptions to Sentry with context:
  ```python
  import sentry_sdk

  try:
      # risky operation
      pass
  except Exception as e:
      sentry_sdk.capture_exception(e)
      raise  # or handle appropriately
  ```
- Report unexpected events or conditions:
  ```python
  sentry_sdk.capture_message("Unexpected condition: webhook config not found", level="warning")
  ```
- Use appropriate Sentry levels: `"debug"`, `"info"`, `"warning"`, `"error"`, `"fatal"`

### Type Annotation Conventions
- Use modern Python 3.13+ type annotation syntax:
  - `dict` instead of `Dict`, `list` instead of `List`
  - `A | None` instead of `Optional[A]`
  - `A | B` instead of `Union[A, B]`
- Import collection types from `collections.abc`:
  ```python
  from collections.abc import Callable, Sequence, Iterable, Generator
  ```
- For type-only imports, use `TYPE_CHECKING` block:
  ```python
  from __future__ import annotations
  from typing import TYPE_CHECKING

  if TYPE_CHECKING:
      from django.db.models import QuerySet
      from some.module import ComplexType
  ```
- Always include `from __future__ import annotations` at the top of files.

### Code Style Conventions
- For user-facing strings, use double quotes; for strings not visible to users, use single quotes.
- Multi-line docstring summaries start on the **second** line (ruff D213):
  ```python
  def foo():
      """
      Summary line here.

      Details...
      """
  ```

### Code Structure Conventions
- **Avoid deeply nested logic** - Prefer flat, readable code over nested conditionals
- **Use early returns** - Check for exceptional/edge cases first and return early
- **Reverse conditionals** - Instead of `if condition: main_logic`, use `if not condition: return` then `main_logic`

**Example - Avoid nesting:**
```python
# Bad: nested logic
def process_request(request):
    if request.user.is_authenticated:
        if request.user.is_active:
            if has_permission(request.user):
                # main logic here
                return do_something()
    return None

# Good: early returns
def process_request(request):
    if not request.user.is_authenticated:
        return None
    if not request.user.is_active:
        return None
    if not has_permission(request.user):
        return None

    # main logic is not nested
    return do_something()
```

### Testing Conventions
- If there is a factory (e.g., `ModelFactory`) registered as a fixture (e.g., `model_factory`), prefer creating objects via `ModelFactory.create()` over `model_factory()`.

### Key Models Hierarchy
- `actions/models/plan.py` - Plan, PlanDomain, PlanFeatures
- `actions/models/action.py` - Action (main entity)
- `actions/models/category.py` - CategoryType, Category for action organization
- `actions/models/attributes.py` - Dynamic attributes system
- `orgs/models.py` - Organization hierarchy
- `people/models.py` - Person, User extensions

### Multi-tenancy via Plan Domains
- Plans are isolated by domain via `PlanDomain` model
- Context filtering throughout the application based on current plan
- Admin interface restricts data access by plan context

### Internationalization (i18n)
- Uses `django-modeltrans` for model field translations
- MJML email templates use Jinja2 (not Django templates)
- Supports multiple locales with separate translation workflows

### Extensions System
- Optional, closed-source `kausal_watch_extensions` package for SaaS-enabling features
- Automatically included in tests and URL routing when available
- Symlinked from separate kausal-extensions repository

### Background Tasks
- Celery for asynchronous task processing
- Redis as message broker
- Task definitions in various `tasks.py` files

## Testing Strategy

### Test Configuration
- Uses pytest with Django integration
- Configuration in `pyproject.toml` under `[tool.pytest.ini_options]`
- Factory Boy for test data generation
- Coverage reporting available

### Type Checking
- MyPy configuration with Django plugin
- Baseline file `.mypy-baseline.txt` for gradual typing adoption
- Type stubs for some 3rd party packages in `kausal_common/typings/`

## API Architecture

### REST API
- Django REST Framework at `/v1/` prefix
- Nested routers for hierarchical resources
- OpenAPI schema available at `/v1/schema/`
- Swagger UI at `/v1/docs/`

### GraphQL API
- Endpoint at `/v1/graphql/`
- GraphQL Voyager documentation at `/v1/graphql/docs/`
- Supports both query and mutation operations
- Plan-based data filtering built into resolvers

## Content Management

### Wagtail CMS Integration
- Page models in `pages/models.py`
- Custom Wagtail blocks in various `blocks/` directories
- Admin interface customizations in `*_wagtail.py` files
- Custom choosers for plan-specific content

### Rich Content Blocks
- Modular content blocks system
- Action content blocks for displaying plan data
- Category listing and filtering blocks
- Custom stream fields for flexible page layouts

## Detailed Architecture Documentation

For in-depth implementation details on specific subsystems, see:

- [MCP Server](docs/architecture/mcp-server.md) - Adding tools, GraphQL integration, authentication flow
- [Plan Metadata Model](docs/architecture/plan-metadata.md) - How climate action plans are structured, including CategoryTypes, Attributes, and common classification systems
