"""Project-wide fixtures — BASE-DESIGN.md §5.2, bodies per APP-DESIGN.md §7.2.

Anything spanning more than one installed app belongs in `core/tests/conftest.py`
instead, not here.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db: None) -> AbstractUser:
    return get_user_model().objects.create_user(username="alice", password="pw")


@pytest.fixture
def admin_user(db: None) -> AbstractUser:
    return get_user_model().objects.create_superuser(username="admin", password="pw")


@pytest.fixture
def auth_client(api_client: APIClient, user: AbstractUser) -> APIClient:
    api_client.force_authenticate(user=user)
    return api_client
