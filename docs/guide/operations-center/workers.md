# Worker 工作节点

## 概述

Worker 进程注册到数据库并轮询部署任务。同机多开须指定不同 `worker_id`。

```bash
flow-worker start
flow-worker start --worker-id hostA-2
```

## 相关文档

- 仓库 [README.md](../../README.md) Worker 章节
