# 安装与访问

## 概述

本地或服务器上启动 **API 服务**、**Web 界面** 与（可选）**Worker** 后即可使用全部功能 Tab 与本帮助文档。

---

## 环境要求

- Python 3.12+（以项目 `pyproject.toml` 为准）
- Node.js 18+（Web 前端开发）
- 可选：`pip install -e ".[integrations]"` 以使用真实 Kafka/HTTP/ES 连接

---

## API 服务

默认地址 `http://127.0.0.1:8000`：

```bash
pip install -e ".[api]"
flow-api
```

健康检查：`GET /api/health`

帮助文档 API：

- `GET /api/guide/tree` — 目录树
- `GET /api/guide/doc?path=...` — 文档正文
- `GET /api/guide/search?q=...` — 全文搜索

---

## Web 界面

默认地址 `http://127.0.0.1:5173`，开发模式将 `/api` 代理到后端：

```bash
cd web
npm install
npm run dev
```

生产构建：

```bash
cd web
npm run build
```

构建产物在 `web/dist`，可由 API 静态托管（以实际部署为准）。

---

## Worker

执行部署的后台进程：

```bash
pip install -e ".[runner]"
flow-worker start --control-url http://127.0.0.1:8000
```

无 Worker 时仍可设计流程、试运行与测试；**部署调度不会真正执行**。

---

## 访问帮助文档

1. 浏览器打开 Web 界面
2. 顶部 Tab 选择 **帮助文档**
3. 左侧浏览目录，或使用顶部搜索框

帮助内容与 `docs/guide/` 目录同步；修改 Markdown 后刷新页面即可（API 实时读取文件）。

---

## 数据库与初始化

首次启动 API 可能自动初始化数据库。维护说明见仓库 `docs/db-reset.md`。

---

## 相关文档

- [第一次试运行](first-trial-run.md)
- [工作节点](../operations-center/workers.md)
- 仓库 [README.md](../../README.md)
