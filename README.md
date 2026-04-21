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

流程定义默认保存在仓库根目录的 `**data/flows/**` 下（每个流程一个 `{id}.yaml`）。可通过环境变量 `**FLOW_ENGINE_FLOWS_DIR**` 指定其他目录；若包不在检出目录中运行，可设置 `**FLOW_ENGINE_REPO_ROOT**` 指向含 `pyproject.toml` 的仓库根，或分别为各资源设置目录类环境变量。

```bash
pip install -e ".[api]"
# 或
flow-api
# 等价于: python -m flow_engine.http_api
```

默认监听 `http://127.0.0.1:8000`，主要接口：


| 方法     | 路径                | 说明                                                                        |
| ------ | ----------------- | ------------------------------------------------------------------------- |
| GET    | `/api/health`     | 健康检查                                                                      |
| GET    | `/api/flows`      | 列出 `data/flows/*.yaml`（或 `FLOW_ENGINE_FLOWS_DIR` 下 `*.yaml`）              |
| GET    | `/api/flows/{id}` | 读取流程（JSON，与前端 `FlowDocument` 一致）                                          |
| PUT    | `/api/flows/{id}` | 保存流程（校验后写回 YAML）                                                          |
| POST   | `/api/flows`      | 新建空流程 `{ "id": "...", "name": "可选" }`                                     |
| DELETE | `/api/flows/{id}` | 删除文件                                                                      |
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
- **边界映射**：改为单一 YAML 风格文本框，顶级键 `inputs:` 与 `outputs:` 分段书写。`#` 开头为注释；inputs 条目形如 `  $.global.alert: alert`，outputs 条目形如 `  summary: $.global.summary`。该格式向后兼容未来在 value 位置追加参数约束 / 校验。
- **调试**：未保存的脚本/边界改动会立即进入「节点调试」面板；调试上下文顶层 key 直接作为 Starlark 全局变量，不走边界映射。

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