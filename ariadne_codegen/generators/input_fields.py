import ast
from typing import Dict, Optional, Tuple

from graphql import (
    BooleanValueNode,
    ConstValueNode,
    EnumValueNode,
    FloatValueNode,
    GraphQLEnumType,
    GraphQLInputObjectType,
    GraphQLList,
    GraphQLNonNull,
    GraphQLScalarType,
    InputValueDefinitionNode,
    IntValueNode,
    ListValueNode,
    NullValueNode,
    ObjectValueNode,
    StringValueNode,
)

from ..exceptions import ParsingError
from .codegen import (
    generate_annotation_name,
    generate_arguments,
    generate_call,
    generate_constant,
    generate_dict,
    generate_keyword,
    generate_lambda,
    generate_list,
    generate_list_annotation,
    generate_method_call,
    generate_name,
)
from .constants import ANY, FIELD_CLASS, SIMPLE_TYPE_MAP
from .scalars import ScalarData
from .types import Annotation, CodegenInputFieldType


# pylint: disable=too-many-return-statements
def parse_input_field_type(
    type_: CodegenInputFieldType,
    nullable: bool = True,
    custom_scalars: Optional[Dict[str, ScalarData]] = None,
) -> Tuple[Annotation, str]:
    if isinstance(type_, GraphQLScalarType):
        if type_.name in SIMPLE_TYPE_MAP:
            return (
                generate_annotation_name(
                    name=SIMPLE_TYPE_MAP[type_.name], nullable=nullable
                ),
                "",
            )

        if custom_scalars and type_.name in custom_scalars:
            return (
                generate_annotation_name(
                    name=custom_scalars[type_.name].type_, nullable=nullable
                ),
                type_.name,
            )

        return generate_annotation_name(name=ANY, nullable=nullable), ""

    if isinstance(type_, GraphQLInputObjectType):
        return (
            generate_annotation_name(name='"' + type_.name + '"', nullable=nullable),
            type_.name,
        )

    if isinstance(type_, GraphQLEnumType):
        return (
            generate_annotation_name(name=type_.name, nullable=nullable),
            type_.name,
        )

    if isinstance(type_, GraphQLList):
        slice_, type_name = parse_input_field_type(
            type_=type_.of_type, nullable=nullable, custom_scalars=custom_scalars
        )
        return generate_list_annotation(slice_=slice_, nullable=nullable), type_name

    if isinstance(type_, GraphQLNonNull):
        return parse_input_field_type(
            type_=type_.of_type, nullable=False, custom_scalars=custom_scalars
        )

    raise ParsingError("Invalid input field type.")


def parse_input_field_default_value(
    node: InputValueDefinitionNode, field_type: str = ""
) -> Optional[ast.expr]:
    if node and node.default_value:
        return parse_input_const_value_node(
            node=node.default_value, field_type=field_type
        )
    return None


# pylint: disable=too-many-return-statements
def parse_input_const_value_node(
    node: ConstValueNode,
    field_type: str = "",
    nested_list=False,
    nested_object=False,
) -> Optional[ast.expr]:
    if isinstance(node, IntValueNode):
        return generate_constant(int(node.value))

    if isinstance(node, FloatValueNode):
        return generate_constant(float(node.value))

    if isinstance(node, StringValueNode):
        return generate_constant(node.value)

    if isinstance(node, BooleanValueNode):
        return generate_constant(bool(node.value))

    if isinstance(node, NullValueNode):
        return generate_constant(None)

    if isinstance(node, EnumValueNode):
        return generate_name(f"{field_type}.{node.value}")

    if isinstance(node, ListValueNode):
        list_ = generate_list(
            [
                parse_input_const_value_node(
                    node=v,
                    field_type=field_type,
                    nested_object=nested_object,
                    nested_list=True,
                )
                for v in node.values
            ]
        )
        if not nested_list:
            return generate_call(
                func=generate_name(FIELD_CLASS),
                keywords=[
                    generate_keyword(
                        arg="default_factory",
                        value=generate_lambda(args=generate_arguments(), body=list_),
                    )
                ],
            )
        return list_

    if isinstance(node, ObjectValueNode):
        dict_ = generate_dict(
            keys=[generate_constant(f.name.value) for f in node.fields],
            values=[
                parse_input_const_value_node(
                    node=f.value,
                    field_type=field_type,
                    nested_object=True,
                    nested_list=True,
                )
                for f in node.fields
            ],
        )
        if not nested_object:
            return generate_method_call(field_type, "parse_obj", [dict_])
        return dict_

    return None
