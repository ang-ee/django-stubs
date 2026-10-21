from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import models
from django.db.backends.sqlite3.base import DatabaseWrapper
from django.db.models import F, OuterRef, Value
from django.db.models.deletion import Collector
from django.db.models.lookups import Exact
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query
from django.test.utils import isolate_apps

from mypy_django_plugin.django.context import DjangoContext


def test_expression_names_and_parameter_shapes_match_django() -> None:
    DjangoContext("scripts.django_tests_settings")
    nested = OuterRef(OuterRef("title"))
    assert isinstance(nested.name, OuterRef)
    assert nested.name.name == F("title").name == "title"
    connection = DatabaseWrapper({"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"})
    compiler = SQLCompiler(Query(models.Model), connection, "default")
    for value in (Decimal("1.25"), date(2026, 1, 1), UUID(int=0), b"value", None):
        sql, params = Value(value).as_sql(compiler, connection)
        assert isinstance(sql, str)
        assert isinstance(params, list)
        if value is None:
            assert sql == "NULL"
            assert params == []
        else:
            assert len(params) == 1
    sql, params = Exact(Value(Decimal("1.25")), Decimal("1.25")).as_sql(compiler, connection)
    assert isinstance(sql, str)
    assert params == (Decimal("1.25"), Decimal("1.25"))


def test_collector_field_updates_store_collections() -> None:
    DjangoContext("scripts.django_tests_settings")
    with isolate_apps():

        class Record(models.Model):
            title = models.CharField()

            class Meta:
                app_label = "expression_contracts"

        collector = Collector("default")
        field = Record._meta.get_field("title")
        row = Record(title="before")
        first = [row]
        second = (row,)
        collector.add_field_update(field, "after", first)
        collector.add_field_update(field, "after", second)
        assert collector.field_updates[field, "after"] == [first, second]
