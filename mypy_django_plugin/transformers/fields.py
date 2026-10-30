from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, cast

from django.core.exceptions import FieldDoesNotExist
from django.db.models.fields import AutoField
from django.db.models.fields.related import RelatedField
from mypy.infer import infer_type_arguments
from mypy.maptype import map_instance_to_supertype
from mypy.nodes import AssignmentStmt, NameExpr, TypeInfo
from mypy.typeops import get_type_vars
from mypy.types import (
    AnyType,
    Instance,
    NoneType,
    ProperType,
    TypeOfAny,
    TypeType,
    UninhabitedType,
    UnionType,
    get_proper_type,
)
from mypy.types import Type as MypyType
from mypy.typevars import fill_typevars

from mypy_django_plugin.exceptions import UnregisteredModelError
from mypy_django_plugin.lib import fullnames, helpers
from mypy_django_plugin.transformers import manytomany

if TYPE_CHECKING:
    from django.db.models.options import _AnyField
    from mypy.plugin import AttributeContext, FunctionContext

    from mypy_django_plugin.django.context import DjangoContext


def _get_current_field_from_assignment(ctx: FunctionContext, django_context: DjangoContext) -> _AnyField | None:
    outer_model_info = helpers.get_typechecker_api(ctx).scope.active_class()
    if outer_model_info is None or not helpers.is_model_type(outer_model_info):
        return None

    field_name = None
    for stmt in outer_model_info.defn.defs.body:
        if isinstance(stmt, AssignmentStmt):
            if stmt.rvalue == ctx.context:
                if not isinstance(stmt.lvalues[0], NameExpr):
                    return None
                field_name = stmt.lvalues[0].name
                break
    if field_name is None:
        return None

    model_cls = django_context.get_model_class_by_fullname(outer_model_info.fullname)
    if model_cls is None:
        return None

    try:
        return model_cls._meta.get_field(field_name)
    except FieldDoesNotExist:
        return None


def reparametrize_related_field_type(related_field_type: Instance, set_type: MypyType, get_type: MypyType) -> Instance:
    mapped = helpers.get_field_type_args(related_field_type)
    assert mapped is not None
    return reparametrize_field_type(
        related_field_type,
        helpers.convert_any_to_type(mapped.set, set_type),
        helpers.convert_any_to_type(mapped.get, get_type),
    )


def fill_descriptor_types_for_related_field(ctx: FunctionContext, django_context: DjangoContext) -> MypyType:
    current_field = _get_current_field_from_assignment(ctx, django_context)
    if current_field is None:
        return AnyType(TypeOfAny.from_error)

    assert isinstance(current_field, RelatedField)

    try:
        related_model_cls = django_context.get_field_related_model_cls(current_field)
    except UnregisteredModelError:
        return AnyType(TypeOfAny.from_error)

    default_related_field_type = set_descriptor_types_for_field(ctx)

    # self reference with abstract=True on the model where ForeignKey is defined
    current_model_cls = current_field.model
    if current_model_cls._meta.abstract and current_model_cls == related_model_cls:
        # for all derived non-abstract classes, set variable with this name to
        # __get__/__set__ of ForeignKey of derived model
        for model_cls in django_context.all_registered_model_classes:
            if issubclass(model_cls, current_model_cls) and not model_cls._meta.abstract:
                derived_model_info = django_context.lookup_model_typeinfo(helpers.get_typechecker_api(ctx), model_cls)
                if derived_model_info is not None:
                    fk_ref_type = Instance(derived_model_info, [])
                    concrete_info = helpers.lookup_class_typeinfo(helpers.get_typechecker_api(ctx), model_cls)
                    fk_get_type = Instance(concrete_info, []) if concrete_info is not None else fk_ref_type
                    derived_fk_type = reparametrize_related_field_type(
                        default_related_field_type, set_type=fk_ref_type, get_type=fk_get_type
                    )
                    helpers.add_new_sym_for_info(derived_model_info, name=current_field.name, sym_type=derived_fk_type)

    typechecker_api = helpers.get_typechecker_api(ctx)
    related_model_to_set_info, related_model_info = django_context.get_related_model_typeinfos(
        typechecker_api, related_model_cls
    )
    related_model_type: ProperType
    if related_model_info is None:
        # maybe no type stub
        related_model_type = AnyType(TypeOfAny.unannotated)
    else:
        related_model_type = Instance(related_model_info, [])

    related_model_to_set_type: ProperType
    if related_model_to_set_info is None:
        # maybe no type stub
        related_model_to_set_type = AnyType(TypeOfAny.unannotated)
    else:
        related_model_to_set_type = Instance(related_model_to_set_info, [])

    # replace Any with referred_to_type
    return reparametrize_related_field_type(
        default_related_field_type, set_type=related_model_to_set_type, get_type=related_model_type
    )


class FieldDescriptorTypes(NamedTuple):
    set: MypyType
    get: MypyType


def get_field_descriptor_types(
    field_info: TypeInfo, *, is_set_nullable: bool, is_get_nullable: bool
) -> FieldDescriptorTypes:
    set_type = helpers.get_private_descriptor_type(field_info, "_pyi_private_set_type", is_nullable=is_set_nullable)
    get_type = helpers.get_private_descriptor_type(field_info, "_pyi_private_get_type", is_nullable=is_get_nullable)
    return FieldDescriptorTypes(set=set_type, get=get_type)


def set_descriptor_types_for_field_callback(ctx: FunctionContext, django_context: DjangoContext) -> MypyType:
    current_field = _get_current_field_from_assignment(ctx, django_context)
    if current_field is not None:
        if isinstance(current_field, AutoField):
            return set_descriptor_types_for_field(ctx, is_set_nullable=True)

    return set_descriptor_types_for_field(ctx)


def set_descriptor_types_for_field(
    ctx: FunctionContext, *, is_set_nullable: bool = False, is_get_nullable: bool = False
) -> Instance:
    default_return_type = cast("Instance", ctx.default_return_type)

    is_nullable = helpers.get_bool_call_argument_by_name(ctx, "null", default=False)
    is_primary_key = helpers.get_bool_call_argument_by_name(ctx, "primary_key", default=False)
    # Allow setting field value to `None` when a field is primary key and has a default that can produce a value
    default_expr = helpers.get_call_argument_by_name(ctx, "default")
    if default_expr is not None:
        is_set_nullable = is_primary_key

    set_type, get_type = get_field_descriptor_types(
        default_return_type.type,
        is_set_nullable=is_set_nullable or is_nullable,
        is_get_nullable=is_get_nullable or is_nullable,
    )

    # reconcile set and get types with the base field class
    mapped_types = helpers.get_field_type_args(default_return_type)
    assert mapped_types is not None

    # bail if either mapped set or get type is Never
    if not (isinstance(mapped_types.set, UninhabitedType) or isinstance(mapped_types.get, UninhabitedType)):
        # always replace set_type and get_type with (non-Any) mapped types
        set_type = helpers.convert_any_to_type(mapped_types.set, set_type)
        get_type = get_proper_type(helpers.convert_any_to_type(mapped_types.get, get_type))

        # the get_type must be optional if the field is nullable
        if (is_get_nullable or is_nullable) and not (
            isinstance(get_type, NoneType) or helpers.is_optional(get_type) or isinstance(get_type, AnyType)
        ):
            ctx.api.fail(
                f"{default_return_type.type.name} is nullable but its generic get type parameter is not optional",
                ctx.context,
            )

    return reparametrize_field_type(default_return_type, set_type, get_type)


def reparametrize_field_type(field_type: Instance, set_type: MypyType, get_type: MypyType) -> Instance:
    """Map descriptor types back through the field subclass's declared generics."""
    generic_field = fill_typevars(field_type.type)
    assert isinstance(generic_field, Instance)
    field_info = next(base for base in generic_field.type.mro if base.fullname == fullnames.FIELD_FULLNAME)
    template = map_instance_to_supertype(generic_field, field_info)
    inferred = infer_type_arguments(
        generic_field.type.defn.type_vars, template, Instance(field_info, [set_type, get_type])
    )
    descriptor_vars = {variable.id for variable in get_type_vars(template)}
    return field_type.copy_modified(
        args=[
            original if variable.id not in descriptor_vars or value is None else value
            for variable, original, value in zip(
                generic_field.type.defn.type_vars, field_type.args, inferred, strict=True
            )
        ]
    )


def determine_type_of_array_field(ctx: FunctionContext, django_context: DjangoContext) -> MypyType:
    default_return_type = set_descriptor_types_for_field(ctx)

    base_field_arg_type = get_proper_type(helpers.get_call_argument_type_by_name(ctx, "base_field"))
    if not base_field_arg_type or not isinstance(base_field_arg_type, Instance):
        return default_return_type

    def drop_combinable(_type: MypyType) -> MypyType | None:
        _type = get_proper_type(_type)
        if isinstance(_type, Instance) and _type.type.has_base(fullnames.COMBINABLE_EXPRESSION_FULLNAME):
            return None
        if isinstance(_type, UnionType):
            items_without_combinable = []
            for item in _type.items:
                reduced = drop_combinable(item)
                if reduced is not None:
                    items_without_combinable.append(reduced)

            if len(items_without_combinable) > 1:
                return UnionType(
                    items_without_combinable,
                    line=_type.line,
                    column=_type.column,
                    is_evaluated=_type.is_evaluated,
                    uses_pep604_syntax=_type.uses_pep604_syntax,
                )
            if len(items_without_combinable) == 1:
                return items_without_combinable[0]
            return None

        return _type

    base_types = helpers.get_field_type_args(base_field_arg_type)
    array_types = helpers.get_field_type_args(default_return_type)
    assert base_types is not None and array_types is not None
    args = []
    new_type: MypyType
    for new_type, default_arg in zip(base_types, array_types, strict=True):
        # Drop any base_field Combinable type
        reduced = drop_combinable(new_type)
        if reduced is None:
            ctx.api.fail(
                f"Can't have ArrayField expecting {fullnames.COMBINABLE_EXPRESSION_FULLNAME!r} as data type",
                ctx.context,
            )
        else:
            new_type = reduced

        args.append(helpers.convert_any_to_type(default_arg, new_type))

    return reparametrize_field_type(default_return_type, args[0], args[1])


def transform_into_proper_return_type(ctx: FunctionContext, django_context: DjangoContext) -> MypyType:
    default_return_type = get_proper_type(ctx.default_return_type)
    assert isinstance(default_return_type, Instance)

    outer_model_info = helpers.get_typechecker_api(ctx).scope.active_class()
    if outer_model_info is None or not helpers.is_model_type(outer_model_info):
        return set_descriptor_types_for_field(ctx)

    assert isinstance(outer_model_info, TypeInfo)

    if default_return_type.type.has_base(fullnames.MANYTOMANY_FIELD_FULLNAME):
        return manytomany.fill_model_args_for_many_to_many_field(
            ctx=ctx, model_info=outer_model_info, django_context=django_context
        )
    if helpers.has_any_of_bases(default_return_type.type, fullnames.RELATED_FIELDS_CLASSES):
        return fill_descriptor_types_for_related_field(ctx, django_context)

    if default_return_type.type.has_base(fullnames.ARRAY_FIELD_FULLNAME):
        return determine_type_of_array_field(ctx, django_context)

    return set_descriptor_types_for_field_callback(ctx, django_context)


def related_model_type(ctx: AttributeContext) -> MypyType:
    """Retain the native forward relation's model when reading its metadata."""
    field = ctx.type
    if not isinstance(field, Instance):
        return ctx.default_attr_type
    relation_info = next((info for info in field.type.mro if info.fullname == fullnames.FOREIGN_OBJECT_FULLNAME), None)
    if relation_info is None:
        return ctx.default_attr_type
    relation = map_instance_to_supertype(field, relation_info)
    getter = get_proper_type(relation.args[1])
    members = [get_proper_type(member) for member in getter.items] if isinstance(getter, UnionType) else [getter]
    models = [member for member in members if not isinstance(member, NoneType)]
    if models and all(isinstance(model, Instance) and helpers.is_model_type(model.type) for model in models):
        return TypeType.make_normalized(UnionType.make_union(models))
    return ctx.default_attr_type
