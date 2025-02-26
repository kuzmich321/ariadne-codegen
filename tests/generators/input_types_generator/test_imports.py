import ast

from graphql import build_ast_schema, parse

from ariadne_codegen.generators.input_types import InputTypesGenerator
from ariadne_codegen.generators.scalars import ScalarData

from ...utils import compare_ast, filter_imports


def test_generate_returns_module_with_enum_imports():
    schema_str = """
    input TestInput {
        field: TestEnum!
    }

    enum TestEnum {
        VAL1
        VAL2
    }
    """
    generator = InputTypesGenerator(
        schema=build_ast_schema(parse(schema_str)), enums_module="enums"
    )
    expected_import = ast.ImportFrom(
        module="enums", names=[ast.alias("TestEnum")], level=1
    )

    module = generator.generate()

    import_ = filter_imports(module)[-1]
    assert compare_ast(import_, expected_import)


def test_generate_returns_module_with_used_custom_scalars_imports():
    schema_str = """
    input TestInput {
        field: SCALARA!
    }

    scalar SCALARA
    """
    generator = InputTypesGenerator(
        schema=build_ast_schema(parse(schema_str)),
        enums_module="enums",
        custom_scalars={
            "SCALARA": ScalarData(type_="ScalarA", import_=".custom_scalars")
        },
    )
    expected_import = ast.ImportFrom(
        module=".custom_scalars", names=[ast.alias("ScalarA")], level=0
    )

    module = generator.generate()

    import_ = filter_imports(module)[-1]
    assert compare_ast(import_, expected_import)
