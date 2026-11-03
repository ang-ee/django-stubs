from __future__ import annotations

from typing import Literal
from unittest import mock

import pytest
from django.db import models
from django.test.utils import isolate_apps

from mypy_django_plugin.django.context import DjangoContext


@pytest.mark.parametrize("name", ["_default_manager", "_base_manager"])
def test_context_manager_selection_preserves_native_options_identity(
    name: Literal["_default_manager", "_base_manager"],
) -> None:
    context = DjangoContext("scripts.django_tests_settings")
    with isolate_apps():

        class Record(models.Model):
            visible = models.Manager()
            raw = models.Manager()

            class Meta:
                app_label = "manager_selection"
                default_manager_name = "visible"
                base_manager_name = "raw"

        expected = Record._meta.default_manager if name == "_default_manager" else Record._meta.base_manager
        assert context.get_model_manager(mock.Mock(), Record, name) is expected


def test_context_manager_selection_preserves_absent_abstract_default() -> None:
    context = DjangoContext("scripts.django_tests_settings")
    with isolate_apps():

        class Abstract(models.Model):
            class Meta:
                abstract = True
                app_label = "manager_selection"

        assert Abstract._meta.default_manager is None
        assert context.get_model_manager(mock.Mock(), Abstract, "_default_manager") is None
