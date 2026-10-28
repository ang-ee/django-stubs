from __future__ import annotations

from unittest import mock

import pytest
from django.db import models
from django.test.utils import isolate_apps
from mypy import build as mypy_build  # noqa: F401 -- initialize mypy's compiled import graph
from mypy.nodes import Block, ClassDef, MypyFile, NameExpr, SymbolTable, SymbolTableNode, TypeInfo
from mypy.plugin import ClassDefContext

from mypy_django_plugin.django.context import DjangoContext
from mypy_django_plugin.transformers.models import ModelClassInitializer


@pytest.mark.parametrize("mapped", [False, True])
def test_runtime_model_lookup_uses_context_identity(mapped: bool) -> None:
    class StaticIdentityContext(DjangoContext):
        def get_model_fullname(self, model_cls: type[models.Model]) -> str:
            return "source_models.Record" if mapped else super().get_model_fullname(model_cls)

    context = StaticIdentityContext("scripts.django_tests_settings")
    with isolate_apps():
        model = type(
            "Record",
            (models.Model,),
            {"__module__": "runtime_models", "Meta": type("Meta", (), {"app_label": "identity"})},
        )
        module_name = "source_models" if mapped else "runtime_models"
        classdef = ClassDef("Record", Block([]))
        classdef.fullname = f"{module_name}.Record"
        info = TypeInfo(SymbolTable(), classdef, module_name)
        classdef.info = info
        module = MypyFile([], [])
        module.names = SymbolTable({"Record": SymbolTableNode(1, info)})
        api = mock.Mock(modules={module_name: module})
        initializer = ModelClassInitializer(ClassDefContext(classdef, NameExpr("Model"), api), context)

        assert context.lookup_model_typeinfo(api, model) is info
        assert initializer.lookup_class_typeinfo_or_incomplete_defn_error(model) is info
        with mock.patch.object(context, "all_registered_model_classes", {model}):
            assert context._model_class_fullnames_by_label_lower["identity.record"] == "runtime_models.Record"
        assert model.__module__ == "runtime_models"


def test_model_identity_does_not_redirect_field_class_lookup() -> None:
    context = DjangoContext("scripts.django_tests_settings")
    classdef = ClassDef("Record", Block([]))
    classdef.info = TypeInfo(SymbolTable(), classdef, "source_models")
    initializer = ModelClassInitializer(ClassDefContext(classdef, NameExpr("Model"), mock.Mock()), context)
    with (
        mock.patch.object(context, "get_model_fullname") as model_identity,
        mock.patch.object(initializer, "lookup_typeinfo_or_incomplete_defn_error") as lookup,
    ):
        initializer.lookup_class_typeinfo_or_incomplete_defn_error(models.CharField)
    model_identity.assert_not_called()
    lookup.assert_called_once_with("django.db.models.fields.CharField")


def test_app_registry_identity_excludes_abstract_model_declarations() -> None:
    context = DjangoContext("scripts.django_tests_settings")
    with isolate_apps():
        abstract = type(
            "AbstractRecord",
            (models.Model,),
            {"__module__": "source_models", "Meta": type("Meta", (), {"app_label": "identity", "abstract": True})},
        )
        concrete = type(
            "Record",
            (abstract,),
            {"__module__": "runtime_models", "Meta": type("Meta", (), {"app_label": "identity"})},
        )
        with mock.patch.object(context, "all_registered_model_classes", {abstract, concrete}):
            assert context.model_class_fullname_for_label("identity.AbstractRecord") is None
            assert context.model_class_fullname_for_label("identity.Record") == "runtime_models.Record"
