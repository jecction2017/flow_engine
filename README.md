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

```bash
pip install -e ".[api]"
# 或
flow-api
# 等价于: python -m flow_engine.http_api
```

默认监听 `http://127.0.0.1:8000`

## Vue Flow Studio

```bash
cd web
npm install
npm run dev
```

## Runner（部署/调度层）Worker 启动

启动一个 Worker 进程（会注册到 `fe_worker`，并轮询 `fe_worker_assignment` 执行部署）：

```bash
pip install -e ".[runner]"
flow-worker start
```

### worker_id 规则（重要）

- **默认稳定 ID**：不传 `--worker-id` 时，默认使用 `FLOW_WORKER_ID`，否则使用当前机器 hostname 作为 `worker_id`。这样**重启不会产生无限新增 worker 行**。
- **同机多开**：在同一台机器启动多个 Worker 时，必须显式指定不同的 `worker_id`：

```bash
flow-worker start --worker-id hostA-1
flow-worker start --worker-id hostA-2
```

- **重复启动保护**：如果同一个 `worker_id` 在 DB 中仍显示为 active 且心跳新鲜，第二个进程会拒绝启动，避免重复执行。
- **强制启动（不推荐）**：若确认 DB 状态是脏的，可加 `--force` 跳过保护：

```bash
flow-worker start --force
```

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