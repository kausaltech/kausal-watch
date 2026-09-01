from django.urls import reverse

import pytest


@pytest.fixture
def indicator_list_url(plan):
    return reverse('indicator-list', args=(plan.pk,))


@pytest.fixture
def indicator_detail_url(plan, indicator):
    return reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})
