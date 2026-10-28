from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from django.apps import AppConfig
from django.test.utils import override_settings
from mypy import build as mypy_build  # noqa: F401 -- initialize mypy's compiled import graph
from mypy.options import Options
from mypy.plugin import ReportConfigContext

from mypy_django_plugin.main import NewSemanalDjangoPlugin


@pytest.fixture
def django_plugin() -> NewSemanalDjangoPlugin:
    options = Options()
    options.config_file = str(Path(__file__).resolve().parents[1] / "mypy.ini")
    return NewSemanalDjangoPlugin(options)


@pytest.mark.parametrize("entry", [None, "django.contrib.auth", "django.contrib.auth.apps.AuthConfig", "instance"])
def test_auth_detection_uses_registered_apps(django_plugin: NewSemanalDjangoPlugin, entry: str | None) -> None:
    app = AppConfig.create("django.contrib.auth") if entry == "instance" else entry
    installed = ["django.contrib.contenttypes", app] if app is not None else []
    with override_settings(INSTALLED_APPS=installed):
        assert django_plugin.django_context.is_contrib_auth_installed is (entry is not None)


@pytest.mark.parametrize("label", ["first", "second"])
def test_app_config_cache_identity_is_serializable(django_plugin: NewSemanalDjangoPlugin, label: str) -> None:
    config = AppConfig("scripts", importlib.import_module("scripts"))
    config.label = label
    with override_settings(INSTALLED_APPS=["django.contrib.contenttypes", config]):
        data = django_plugin.report_config_data(ReportConfigContext("example", "example.py", False))

    assert json.loads(json.dumps(data))["INSTALLED_APPS"] == [
        "django.contrib.contenttypes",
        {"name": "scripts", "label": label, "config": "django.apps.config.AppConfig"},
    ]
