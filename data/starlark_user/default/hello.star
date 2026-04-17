"""用户脚本示例：user://default/hello.star"""

load("internal://lib/helpers.star", "double_int", "prefix_key")

sum = demo_add(1,2)
di = double_int(2)
app_name = dict_get("app.name")

def greet(who):
    return "hello, " + who

{
  "sum": sum,
  "di": di,
  "app_name": app_name,
  "greet": greet("tom"),
}
