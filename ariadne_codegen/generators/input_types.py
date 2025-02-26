import ast
from collections import defaultdict
from typing import Dict, List, Optional, cast

from graphql import (
    GraphQLEnumType,
    GraphQLInputObjectType,
    GraphQLScalarType,
    GraphQLSchema,
)

from .codegen import (
    generate_ann_assign,
    generate_class_def,
    generate_expr,
    generate_field_with_alias,
    generate_import_from,
    generate_keyword,
    generate_method_call,
    generate_module,
)
from .constants import (
    ANY,
    BASE_MODEL_CLASS_NAME,
    FIELD_CLASS,
    LIST,
    OPTIONAL,
    PYDANTIC_MODULE,
    TYPING_MODULE,
    UNION,
    UPDATE_FORWARD_REFS_METHOD,
)
from .input_fields import parse_input_field_default_value, parse_input_field_type
from .scalars import ScalarData
from .utils import str_to_snake_case


class InputTypesGenerator:
    def __init__(
        self,
        schema: GraphQLSchema,
        enums_module: str,
        convert_to_snake_case: bool = True,
        base_model_import: Optional[ast.ImportFrom] = None,
        custom_scalars: Optional[Dict[str, ScalarData]] = None,
    ) -> None:
        self.schema = schema
        self.convert_to_snake_case = convert_to_snake_case
        self.enums_module = enums_module
        self.custom_scalars = custom_scalars if custom_scalars else {}

        self._imports = [
            generate_import_from([OPTIONAL, ANY, UNION, LIST], TYPING_MODULE),
            generate_import_from([FIELD_CLASS], PYDANTIC_MODULE),
            base_model_import
            or generate_import_from([BASE_MODEL_CLASS_NAME], PYDANTIC_MODULE),
        ]
        self._dependencies: Dict[str, List[str]] = defaultdict(list)
        self._used_enums: List[str] = []
        self._used_scalars: List[str] = []
        self._class_defs: List[ast.ClassDef] = [
            self._parse_input_definition(d) for d in self._filter_input_types()
        ]

    def generate(self) -> ast.Module:
        if self._used_enums:
            self._imports.append(
                generate_import_from(self._used_enums, self.enums_module, 1)
            )

        if self._used_scalars:
            for scalar_name in self._used_scalars:
                scalar_data = self.custom_scalars[scalar_name]
                if scalar_data.import_:
                    self._imports.append(
                        generate_import_from(
                            names=scalar_data.names_to_import, from_=scalar_data.import_
                        )
                    )
        sorted_class_defs = self._get_sorted_class_defs()
        update_forward_refs_calls = [
            generate_expr(generate_method_call(c.name, UPDATE_FORWARD_REFS_METHOD))
            for c in sorted_class_defs
        ]
        module_body = (
            cast(List[ast.stmt], self._imports)
            + cast(List[ast.stmt], sorted_class_defs)
            + cast(List[ast.stmt], update_forward_refs_calls)
        )

        return generate_module(body=module_body)

    def get_generated_public_names(self) -> List[str]:
        return [c.name for c in self._class_defs]

    def _filter_input_types(self) -> List[GraphQLInputObjectType]:
        return [
            definition
            for name, definition in self.schema.type_map.items()
            if isinstance(definition, GraphQLInputObjectType)
            and not name.startswith("__")
        ]

    def _parse_input_definition(
        self, definition: GraphQLInputObjectType
    ) -> ast.ClassDef:
        class_def = generate_class_def(
            name=definition.name, base_names=[BASE_MODEL_CLASS_NAME]
        )

        for lineno, (org_name, field) in enumerate(definition.fields.items(), start=1):
            name = self._process_field_name(org_name)
            annotation, field_type = parse_input_field_type(
                field.type, custom_scalars=self.custom_scalars
            )
            field_implementation = generate_ann_assign(
                target=name,
                annotation=annotation,
                value=parse_input_field_default_value(
                    node=field.ast_node, field_type=field_type
                ),
                lineno=lineno,
            )
            if name != org_name:
                field_implementation.value = self._process_field_value(
                    field_implementation=field_implementation, alias=org_name
                )

            class_def.body.append(field_implementation)
            self._save_used_enums_scalars_and_dependencies(
                class_name=class_def.name, field_type=field_type
            )

        return class_def

    def _process_field_name(self, name: str) -> str:
        if self.convert_to_snake_case:
            return str_to_snake_case(name)
        return name

    def _process_field_value(
        self,
        field_implementation: ast.AnnAssign,
        alias: str,
    ) -> ast.Call:
        field_with_alias = generate_field_with_alias(alias)
        if field_implementation.value:
            if (
                isinstance(field_implementation.value, ast.Call)
                and isinstance(field_implementation.value.func, ast.Name)
                and field_implementation.value.func.id == FIELD_CLASS
            ):
                field_with_alias.keywords.extend(field_implementation.value.keywords)
            else:
                field_with_alias.keywords.append(
                    generate_keyword(
                        arg="default",
                        value=field_implementation.value,
                    )
                )
        return field_with_alias

    def _save_used_enums_scalars_and_dependencies(
        self, class_name: str, field_type: str = ""
    ) -> None:
        if not field_type:
            return
        if isinstance(self.schema.type_map[field_type], GraphQLInputObjectType):
            self._dependencies[class_name].append(field_type)
        elif isinstance(self.schema.type_map[field_type], GraphQLEnumType):
            self._used_enums.append(field_type)
        elif isinstance(self.schema.type_map[field_type], GraphQLScalarType):
            self._used_scalars.append(field_type)

    def _get_sorted_class_defs(self) -> List[ast.ClassDef]:
        input_class_defs_dict_ = {c.name: c for c in self._class_defs}

        processed_names = []
        for class_ in self._class_defs:
            if class_.name not in processed_names:
                processed_names.extend(self._get_dependant_names(class_.name))
                processed_names.append(class_.name)

        names_without_duplicates = self._get_list_without_duplicates(processed_names)
        return [input_class_defs_dict_[n] for n in names_without_duplicates]

    def _get_dependant_names(self, name: str) -> List[str]:
        result = []
        for dependency_name in self._dependencies[name]:
            result.extend(self._get_dependant_names(dependency_name))
            result.append(dependency_name)
        return result

    def _get_list_without_duplicates(self, list_: list) -> list:
        result = []
        for element in list_:
            if not element in result:
                result.append(element)
        return result
