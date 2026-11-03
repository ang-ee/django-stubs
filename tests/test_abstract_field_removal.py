from __future__ import annotations

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.test.utils import isolate_apps

from mypy_django_plugin.django.context import DjangoContext


def test_abstract_field_removal_uses_native_model_metadata() -> None:
    DjangoContext("scripts.django_tests_settings")
    with isolate_apps():

        class Counter(models.Model):
            revision = models.PositiveIntegerField(default=1)

            class Meta:
                abstract = True
                app_label = "field_removal"

        class RenamedCounter(Counter):
            revision = None
            account_revision = models.PositiveIntegerField(default=1)

            class Meta:
                app_label = "field_removal"

        class KeptCounter(Counter):
            class Meta:
                app_label = "field_removal"

        with pytest.raises(FieldDoesNotExist):
            RenamedCounter._meta.get_field("revision")
        assert RenamedCounter().revision is None
        assert RenamedCounter().account_revision == 1
        assert KeptCounter._meta.get_field("revision").default == 1
        assert Counter._meta.get_field("revision").default == 1
