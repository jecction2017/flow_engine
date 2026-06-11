# 副作用 builtin

## 概述

「副作用」指调用会对外部系统产生影响，或对系统状态产生持久影响的行为。

## 典型例子

- **外部调用**：HTTP 请求、调用集成平台接口（integration）
- **写入**：写数据库（db_write）、发布 MQ（mq_publish）
- **有风险读取**：某些跨租户/跨环境读取（由策略决定是否需要约束）

## 进阶

具体哪些 builtin 属于副作用，由后端 builtin 规格字段 `side_effects` 标记；只有 `side_effects != "none"` 的 builtin 才会触发能力检查。

## 相关文档

- [默认抑制行为](default-behavior.md)
