from __future__ import annotations

from uuid import UUID

import pytest
from django.db import models
from django.test.utils import isolate_apps

from mypy_django_plugin.django.context import DjangoContext


@pytest.mark.parametrize(
    ("field", "value"), [(models.AutoField, 42), (models.UUIDField, UUID(int=1)), (models.CharField, "key")]
)
def test_primary_key_helper_uses_concrete_and_parent_metadata(field: type[models.Field], value: object) -> None:
    DjangoContext("scripts.django_tests_settings")
    with isolate_apps():
        parent = type(
            "Parent",
            (models.Model,),
            {
                "__module__": __name__,
                "id": field(primary_key=True),
                "Meta": type("Meta", (), {"app_label": "primary_key_metadata"}),
            },
        )
        child_type = type(
            "Child",
            (parent,),
            {"__module__": __name__, "Meta": type("Meta", (), {"app_label": "primary_key_metadata"})},
        )
        child = child_type(id=value)
        child.pk = value
        assert child._get_pk_val() == value
        assert child._get_pk_val(child_type._meta) == value
        assert child._get_pk_val(parent._meta) == value


@pytest.mark.parametrize(
    ("field", "value"), [(models.AutoField, 42), (models.UUIDField, UUID(int=1)), (models.CharField, "key")]
)
def test_primary_key_setter_matches_property_and_accepts_none(field: type[models.Field], value: object) -> None:
    DjangoContext("scripts.django_tests_settings")
    with isolate_apps():
        record_type = type(
            "Record",
            (models.Model,),
            {
                "__module__": __name__,
                "id": field(primary_key=True),
                "Meta": type("Meta", (), {"app_label": "primary_key_metadata"}),
            },
        )
        row = record_type()
        assert row._set_pk_val(value) is None
        assert row.pk == value
        row._set_pk_val(None)
        assert row.pk is None


def test_abstract_self_relation_without_primary_key_uses_unknown_pk_contract() -> None:
    context = DjangoContext("scripts.django_tests_settings")
    with isolate_apps():

        class Abstract(models.Model):
            parent = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
            count = models.IntegerField()

            class Meta:
                abstract = True
                app_label = "abstract_pk_contract"

        assert context.resolve_lookup_into_field(Abstract, "pk") == (None, Abstract)
        assert context.resolve_lookup_into_field(Abstract, "parent_id") == (None, Abstract)
        assert context.solve_lookup_type(Abstract, "parent_id__in") is None
        assert context.solve_lookup_type(Abstract, "parent__isnull") is not None
        field, owner = context.resolve_lookup_into_field(Abstract, "count")
        assert field is Abstract._meta.get_field("count")
        assert owner is Abstract
