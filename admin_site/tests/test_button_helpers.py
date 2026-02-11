from __future__ import annotations

from unittest.mock import Mock

from django.test import RequestFactory

import pytest

from admin_site.wagtail import QueryParameterButtonHelper


class ConcreteQueryParameterButtonHelper(QueryParameterButtonHelper):
    """Concrete implementation for testing the base class."""

    parameter_name = 'test_param'


@pytest.fixture
def url_helper():
    """Mock URL helper with action URL methods."""
    helper = Mock()
    helper.create_url = '/admin/create/'
    helper.get_action_url = Mock(side_effect=lambda action, pk: f'/admin/{action}/{pk}/')
    return helper


@pytest.fixture
def permission_helper():
    """Mock permission helper."""
    return Mock()


@pytest.fixture
def view(url_helper, permission_helper):
    """Mock view with required attributes."""
    mock_view = Mock()
    mock_view.url_helper = url_helper
    mock_view.permission_helper = permission_helper
    mock_view.model = Mock()
    mock_view.model._meta = Mock()
    mock_view.model._meta.verbose_name = 'test object'
    mock_view.model._meta.verbose_name_plural = 'test objects'
    return mock_view


@pytest.fixture
def rf():
    """Django request factory."""
    return RequestFactory()


@pytest.fixture
def helper_with_param(view, rf):
    """Button helper with the query parameter present."""
    request = rf.get('/admin/?test_param=123')
    return ConcreteQueryParameterButtonHelper(view, request)


@pytest.fixture
def helper_without_param(view, rf):
    """Button helper without the query parameter."""
    request = rf.get('/admin/')
    return ConcreteQueryParameterButtonHelper(view, request)


class TestQueryParameterButtonHelperAddButton:
    """Tests for the add_button method."""

    def test_add_button_returns_none_when_parameter_missing(self, helper_without_param):
        """Should return None when the query parameter is not present."""
        result = helper_without_param.add_button()
        assert result is None

    def test_add_button_returns_dict_when_parameter_present(self, helper_with_param):
        """Should return button dict when the query parameter is present."""
        result = helper_with_param.add_button()
        assert result is not None
        assert isinstance(result, dict)
        assert 'url' in result
        assert 'label' in result

    def test_add_button_appends_query_parameter_to_url(self, helper_with_param):
        """Should append the query parameter to the URL."""
        result = helper_with_param.add_button()
        assert result['url'] == '/admin/create/?test_param=123'

    def test_add_button_preserves_parameter_value(self, view, rf):
        """Should preserve the exact parameter value from the request."""
        request = rf.get('/admin/?test_param=custom_value')
        helper = ConcreteQueryParameterButtonHelper(view, request)
        result = helper.add_button()
        assert result['url'] == '/admin/create/?test_param=custom_value'


class TestQueryParameterButtonHelperInspectButton:
    """Tests for the inspect_button method."""

    def test_inspect_button_appends_query_parameter(self, helper_with_param):
        """Should append the query parameter to the inspect URL."""
        result = helper_with_param.inspect_button(pk=42)
        assert result['url'] == '/admin/inspect/42/?test_param=123'

    def test_inspect_button_works_without_parameter(self, helper_without_param):
        """Should work but not append parameter when it's not present."""
        result = helper_without_param.inspect_button(pk=42)
        # URL should not have query parameter appended
        assert result['url'] == '/admin/inspect/42/'


class TestQueryParameterButtonHelperEditButton:
    """Tests for the edit_button method."""

    def test_edit_button_appends_query_parameter(self, helper_with_param):
        """Should append the query parameter to the edit URL."""
        result = helper_with_param.edit_button(pk=42)
        assert result['url'] == '/admin/edit/42/?test_param=123'

    def test_edit_button_works_without_parameter(self, helper_without_param):
        """Should work but not append parameter when it's not present."""
        result = helper_without_param.edit_button(pk=42)
        assert result['url'] == '/admin/edit/42/'


class TestQueryParameterButtonHelperDeleteButton:
    """Tests for the delete_button method."""

    def test_delete_button_appends_query_parameter(self, helper_with_param):
        """Should append the query parameter to the delete URL."""
        result = helper_with_param.delete_button(pk=42)
        assert result['url'] == '/admin/delete/42/?test_param=123'

    def test_delete_button_works_without_parameter(self, helper_without_param):
        """Should work but not append parameter when it's not present."""
        result = helper_without_param.delete_button(pk=42)
        assert result['url'] == '/admin/delete/42/'


class TestQueryParameterButtonHelperWithDifferentParameterNames:
    """Tests for button helpers with different parameter names."""

    def test_content_type_parameter(self, view, rf):
        """Test with content_type parameter (AttributeTypeAdminButtonHelper pattern)."""

        class ContentTypeButtonHelper(QueryParameterButtonHelper):
            parameter_name = 'content_type'

        request = rf.get('/admin/?content_type=action')
        helper = ContentTypeButtonHelper(view, request)

        add_result = helper.add_button()
        assert add_result is not None
        assert 'content_type=action' in add_result['url']

        edit_result = helper.edit_button(pk=1)
        assert 'content_type=action' in edit_result['url']

    def test_category_type_parameter(self, view, rf):
        """Test with category_type parameter (CategoryAdminButtonHelper pattern)."""

        class CategoryTypeButtonHelper(QueryParameterButtonHelper):
            parameter_name = 'category_type'

        request = rf.get('/admin/?category_type=5')
        helper = CategoryTypeButtonHelper(view, request)

        add_result = helper.add_button()
        assert add_result is not None
        assert 'category_type=5' in add_result['url']

        inspect_result = helper.inspect_button(pk=10)
        assert 'category_type=5' in inspect_result['url']

    def test_report_type_parameter(self, view, rf):
        """Test with report_type parameter (ReportAdminButtonHelper pattern)."""

        class ReportTypeButtonHelper(QueryParameterButtonHelper):
            parameter_name = 'report_type'

        request = rf.get('/admin/?report_type=annual')
        helper = ReportTypeButtonHelper(view, request)

        add_result = helper.add_button()
        assert add_result is not None
        assert 'report_type=annual' in add_result['url']

        delete_result = helper.delete_button(pk=20)
        assert 'report_type=annual' in delete_result['url']


class TestQueryParameterButtonHelperEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_handles_numeric_parameter_values(self, view, rf):
        """Should correctly handle numeric parameter values."""
        request = rf.get('/admin/?test_param=999')
        helper = ConcreteQueryParameterButtonHelper(view, request)
        result = helper.add_button()
        assert result['url'] == '/admin/create/?test_param=999'

    def test_handles_string_with_special_characters(self, view, rf):
        """Should handle parameter values with special characters."""
        # URL encoding should be handled by Django's URL system
        request = rf.get('/admin/?test_param=test-value_123')
        helper = ConcreteQueryParameterButtonHelper(view, request)
        result = helper.add_button()
        assert 'test_param=test-value_123' in result['url']

    def test_preserves_button_attributes_from_parent(self, helper_with_param):
        """Should preserve all button attributes from the parent class."""
        result = helper_with_param.edit_button(pk=42)
        # Check that parent class attributes are preserved
        assert 'label' in result
        assert 'classname' in result
        assert 'title' in result
        # And our query parameter is added
        assert '?test_param=123' in result['url']
