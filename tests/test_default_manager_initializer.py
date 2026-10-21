from __future__ import annotations

import os
from unittest import mock

import django
import pytest
from django.db import models
from django.test.utils import isolate_apps
from mypy import build as mypy_build  # noqa: F401 -- initialize mypy's compiled import graph
from mypy.nodes import Block, ClassDef, NameExpr, SymbolTable, TypeInfo
from mypy.plugin import ClassDefContext

from mypy_django_plugin.transformers.models import AddDefaultManagerAttribute


@pytest.mark.parametrize(("abstract", "explicit_manager"), [(True, False), (True, True), (False, False)])
def test_default_manager_initializer_uses_only_existing_managers(abstract: bool, explicit_manager: bool) -> None:
    with mock.patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "scripts.django_tests_settings"}):
        django.setup()
    with isolate_apps():
        model = type(
            "Example",
            (models.Model,),
            {
                "__module__": __name__,
                "Meta": type("Meta", (), {"abstract": abstract, "app_label": "initializer"}),
                **({"objects": models.Manager()} if explicit_manager else {}),
            },
        )
        classdef = ClassDef("Example", Block([]))
        classdef.info = TypeInfo(SymbolTable(), classdef, "initializer")
        initializer = AddDefaultManagerAttribute(ClassDefContext(classdef, NameExpr("Model"), mock.Mock()), mock.Mock())
        with (
            mock.patch.object(initializer, "lookup_typeinfo_or_incomplete_defn_error") as lookup,
            mock.patch.object(initializer, "add_new_var_to_model_class") as add_var,
            mock.patch("mypy_django_plugin.transformers.models.helpers.fill_manager") as fill_manager,
        ):
            initializer.run_with_model_cls(model)

        if abstract and not explicit_manager:
            assert model._meta.default_manager is None
            lookup.assert_not_called()
            add_var.assert_not_called()
        else:
            assert isinstance(model._meta.default_manager, models.Manager)
            lookup.assert_called_once_with("django.db.models.manager.Manager")
            assert fill_manager.call_args.args[1].type is classdef.info
            add_var.assert_called_once_with("_default_manager", fill_manager.return_value, is_classvar=True)
