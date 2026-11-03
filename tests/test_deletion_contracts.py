from __future__ import annotations

from django.db.models.deletion import ProtectedError, RestrictedError, get_candidate_relations_to_delete
from django.db.models.fields.reverse_related import ForeignObjectRel

from mypy_django_plugin.django.context import DjangoContext


def test_deletion_candidates_are_native_reverse_relations() -> None:
    DjangoContext("scripts.django_tests_settings")
    from django.contrib.contenttypes.models import ContentType

    candidates = list(get_candidate_relations_to_delete(ContentType._meta))
    assert candidates
    for relation in candidates:
        assert isinstance(relation, ForeignObjectRel)
        assert relation.auto_created and not relation.concrete
        assert relation.one_to_one or relation.one_to_many
        assert relation.field.is_relation


def test_deletion_errors_retain_supplied_iterable() -> None:
    DjangoContext("scripts.django_tests_settings")
    from django.contrib.contenttypes.models import ContentType

    row = ContentType(id=1, app_label="typing", model="record")
    for objects in ({row}, (row,), [row], iter([row])):
        error = ProtectedError("blocked", objects)
        assert error.protected_objects is objects
        restricted = RestrictedError("blocked", objects)
        assert restricted.restricted_objects is objects
