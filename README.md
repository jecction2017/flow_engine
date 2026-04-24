# flow_engine

## Python 编排引擎

```bash
pip install -e .
python -m flow_engine examples/cyber_alert_diagnosis.yaml
```

## 测试

跑所有测试用例

```bash
pip install -e ".[dev,api]"
python -m pytest tests
```

若未做可编辑安装，可临时指定源码路径：

```bash
$env:PYTHONPATH = "e:\cursor\flow_engine\src"
pytest
```

跑某一个测试文件

```bash
pytest tests\test_smoke.py
```

## HTTP API（YAML 文件存储）

流程定义默认保存在仓库根目录的 `**data/flows/`** 下（每个流程一个 `{id}.yaml`）。可通过环境变量 `**FLOW_ENGINE_FLOWS_DIR**` 指定其他目录；若包不在检出目录中运行，可设置 `**FLOW_ENGINE_REPO_ROOT**` 指向含 `pyproject.toml` 的仓库根，或分别为各资源设置目录类环境变量。

```bash
pip install -e ".[api]"
# 或
flow-api
# 等价于: python -m flow_engine.http_api
```

默认监听 `http://127.0.0.1:8000`，主要接口：


| 方法     | 路径                | 说明                                                                                                             |
| ------ | ----------------- | -------------------------------------------------------------------------------------------------------------- |
| GET    | `/api/health`     | 健康检查                                                                                                           |
| GET    | `/api/flows`      | 列出 `data/flows/*.yaml`（或 `FLOW_ENGINE_FLOWS_DIR` 下 `*.yaml`）                                                   |
| GET    | `/api/flows/{id}` | 读取流程（JSON，与前端 `FlowDocument` 一致）                                                                               |
| PUT    | `/api/flows/{id}` | 保存流程（校验后写回 YAML）                                                                                               |
| POST   | `/api/flows`      | 新建空流程 `{ "id": "...", "name": "可选" }`                                                                          |
| DELETE | `/api/flows/{id}` | 删除文件                                                                                                           |
| POST   | `/api/debug/node` | 调试 Task 节点 Starlark（body: `script`, `initial_context`；调试态直接将 `initial_context` 顶层 key 作为 Starlark 全局变量，不做边界映射） |


## Vue Flow Studio

```bash
cd web
npm install
npm run dev
```

开发时 Vite 将 `/api` 代理到 `127.0.0.1:8000`，需先启动上述 API 服务后再使用「保存到服务器」与列表加载。

### 节点定义约定

- **id（逻辑主键，必填）**：正则 `^[A-Za-z][A-Za-z0-9_]*$`。节点在一个流程内 id 全局唯一，是引用/跳转/调试上下文的稳定键。
- **name（显示名，可选）**：仅用于可视化展示，允许中文与任意字符。默认与 id 相同，可单独改写。
- **边界映射**：改为单一 YAML 风格文本框，顶级键 `inputs:` 与 `outputs:` 分段书写。`#` 开头为注释；inputs 条目形如   `$.global.alert: alert`，outputs 条目形如   `summary: $.global.summary`。该格式向后兼容未来在 value 位置追加参数约束 / 校验。
- **调试**：未保存的脚本/边界改动会立即进入「节点调试」面板；调试上下文顶层 key 直接作为 Starlark 全局变量，不走边界映射。

## 节点日志（log / log_info / log_warn / log_error）

为了便于调试复杂流程，引擎在 Starlark 运行时里注入了一组无副作用的日志函数，脚本中可以随时打印节点内部执行情况；日志**仅随本次运行的响应体返回前端**，不落盘、不写进程 `logging`。

- **可用函数**：
  - `log(*args, level="info")` — 可变参，按空格拼接；支持 dict/list（自动 JSON 序列化）。
  - `log_info(*args)` / `log_warn(*args)` / `log_error(*args)` / `log_debug(*args)` — 固定级别的快捷函数。
- **可用位置**：任何 task 脚本、flow / 节点 / loop / subflow 的 `on_start`、`on_complete`、`on_failure`、`pre_exec`、`post_exec`、`on_iteration_start`、`on_iteration_end`、`on_error:custom`。在 `condition` / `loop.iterable` 表达式中调用不会报错，但日志会被丢弃（归属不明确）。
- **归属**：
  - 节点脚本 + 节点级 hook 日志挂在对应节点的 `node_runs[*].logs[]`；每条带 `source`（`task` / `pre_exec` / `post_exec` / `on_iteration_`* / `on_error`）与 `level`。
  - 重试运行时附加 `attempt` 字段（从 1 开始；首次运行不带）。
  - flow 级 hook（`on_start` / `on_complete` / `on_failure`）日志挂在响应体顶层 `flow_logs[]`。
- **查看**：
  - 「节点调试」面板（`/api/debug/node`）的「运行日志」区块。
  - 「流程运行结果」面板（`/api/flows/{id}/run`）中，时间线每一行带日志时会显示 `📝 N` 按钮，点击展开当前节点的日志抽屉；顶部工具条里的「日志级别」胶囊可按级别过滤；底部有独立的「流程级日志」面板。
- **限额环境变量**：
  - `FLOW_ENGINE_STARLARK_LOG_MAX_ENTRIES`（默认 `500`）：单次脚本/hook 作用域内最多保留的日志条数，超出部分丢弃并在最后一条保留条目上标记 `truncated=true`。
  - `FLOW_ENGINE_STARLARK_LOG_MAX_MSG`（默认 `2048`）：单条日志消息最大字符数，超长会在末尾截断并追加 `…`。

## cursor访问外部大模型

用快捷键 command + shift + P 然后搜索 open user settings 选择带json 的那个，然后在json中添加下面：

```bash
"workbench.editor.enablePreview": false,
"http.proxy": "http://127.0.0.1:6699",
"http.proxyStrictSSL": false,
"http.proxySupport": "override",
"http.noProxy": [],
"cursor.general.disableHttp2": true
```

http.proxy修改为本地代理的端口