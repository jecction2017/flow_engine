"""用户脚本示例：user://default/hello.star"""

# 加载内置starlark脚本
load("internal://lib/helpers.star", "double_int", "prefix_key")
# 调用内置python函数
sum = demo_add(1,2)
app_name = dict_get("app.name")
# 调用内置starlark函数
di = double_int(2)
# 函数定义
def greet(who):
    return "hello, " + who
# 返回值必须是dict
{
  "sum": sum,
  "di": di,
  "app_name": app_name,
  "greet": greet("tom"),
}
