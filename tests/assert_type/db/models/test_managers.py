"""Regression test for https://github.com/typeddjango/django-stubs/issues/2911.

A TypeVar with a forward-referenced bound used in a QuerySet subclass
caused 'Must not defer during final iteration' crash in mypy.
"""

from __future__ import annotations

from typing import assert_type

from django.db import models
from django.db.models.query import QuerySet
from typing_extensions import TypeVar

T = TypeVar("T", bound="MyModel")


class MyModelQuerySet(QuerySet[T]):
    pass


class MyModel(models.Model):
    class Meta:
        app_label = "myapp"


class CustomManager(models.Manager["OtherModel"]):
    def manager_method(self) -> str:
        return ""


class OtherQuerySet(models.QuerySet["OtherModel"]): ...


class OtherModel(models.Model):
    class Meta:
        app_label = "myapp"


# `from_queryset` returns `type[Self]`, preserving manager subclasses and their members
assert_type(CustomManager.from_queryset(OtherQuerySet), type[CustomManager])
assert_type(CustomManager.from_queryset(OtherQuerySet)().manager_method(), str)


# Django's Manager is built by BaseManager.from_queryset(QuerySet); factories
# keep the model binding on the native queryset-class attribute.
assert_type(models.Manager[OtherModel]()._queryset_class, type[QuerySet[OtherModel]])
assert_type(CustomManager.from_queryset(OtherQuerySet)()._queryset_class, type[QuerySet[OtherModel]])
assert_type(CustomManager.from_queryset(OtherQuerySet)()._queryset_class(model=OtherModel).first(), OtherModel | None)
