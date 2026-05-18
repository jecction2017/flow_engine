from flow_engine.starlark_sdk.user_script_exports import extract_starlark_export_functions


def test_extract_starlark_export_functions_dedupes_and_preserves_order() -> None:
    src = '''
def b(x):
    return x

def a():
    pass

def b(y):
    return y
'''
    assert extract_starlark_export_functions(src) == ["b", "a"]


def test_extract_starlark_export_functions_empty() -> None:
    assert extract_starlark_export_functions("") == []
    assert extract_starlark_export_functions('load("x")\n{"ok": True}\n') == []
