"""示例内置 Starlark 库（internal://lib/helpers.star）。"""


def double_int(x):
    return x * 2


def prefix_key(d, p):
    """将 dict 的每个 key 加上前缀 p（一层浅键）。"""
    return {p + k: d[k] for k in d}
