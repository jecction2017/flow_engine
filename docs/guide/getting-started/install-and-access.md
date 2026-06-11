# 安装与访问

## 概述

本地或服务器上启动 API 与 Web 界面后即可使用帮助文档与各功能 Tab。

## 操作步骤

**API 服务**（默认 `http://127.0.0.1:8000`）：

```bash
pip install -e ".[api]"
flow-api
```

**Web 界面**（默认 `http://127.0.0.1:5173`，代理 `/api` 到后端）：

```bash
cd web
npm install
npm run dev
```

**Worker**（执行部署）：

```bash
pip install -e ".[runner]"
flow-worker start
```

## 相关文档

- 仓库 [README.md](../../README.md)
