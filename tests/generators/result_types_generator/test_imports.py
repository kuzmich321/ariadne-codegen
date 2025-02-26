import ast
from typing import cast

from graphql import OperationDefinitionNode, build_ast_schema, parse

from ariadne_codegen.generators.result_types import ResultTypesGenerator
from ariadne_codegen.generators.scalars import ScalarData

from ...utils import compare_ast, filter_imports
from .schema import SCHEMA_STR


def test_generate_returns_module_with_enum_imports():
    query_str = """
    query CustomQuery {
        query2 {
            field3
        }
    }
    """
    operation_definition = cast(
        OperationDefinitionNode, parse(query_str).definitions[0]
    )
    generator = ResultTypesGenerator(
        schema=build_ast_schema(parse(SCHEMA_STR)),
        operation_definition=operation_definition,
        enums_module_name="enums",
    )

    module = generator.generate()

    assert isinstance(module, ast.Module)
    import_ = filter_imports(module)[-1]
    assert compare_ast(
        import_,
        ast.ImportFrom(module="enums", names=[ast.alias("CustomEnum")], level=1),
    )


def test_generate_returns_module_with_used_custom_scalars_imports():
    query_str = """
    query CustomQuery {
        camelCaseQuery {
            scalarField
        }
    }
    """
    operation_definition = cast(
        OperationDefinitionNode, parse(query_str).definitions[0]
    )
    generator = ResultTypesGenerator(
        schema=build_ast_schema(parse(SCHEMA_STR)),
        operation_definition=operation_definition,
        enums_module_name="enums",
        custom_scalars={
            "SCALARA": ScalarData(type_="ScalarA", import_=".custom_scalars")
        },
    )
    expected_import = ast.ImportFrom(
        module=".custom_scalars", names=[ast.alias("ScalarA")], level=0
    )

    module = generator.generate()

    assert isinstance(module, ast.Module)
    import_ = filter_imports(module)[-1]
    assert compare_ast(import_, expected_import)
