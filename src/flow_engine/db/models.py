"""SQLAlchemy 2.0 declarative models.

表设计规范：
  - 表名前缀 fe_（flow engine 业务模块）
  - 主键：统一 id BIGINT UNSIGNED AUTO_INCREMENT；另设业务唯一键（flow_code、profile_code、(profile_code, ns_code) 等），子表关联父表的业务键，便于迁移对账而不必依赖自增 id 语义。
  - 审计字段：created_at / updated_at / deleted_at / version / created_by / updated_by
  - 无外键约束，引用完整性由应用层保证
  - 字符集：utf8mb4 / utf8mb4_unicode_ci / InnoDB
  - 反范式：fe_flow.display_name / latest_ver_no / has_draft 等冗余字段仅用于列表与统计，以读性能换写入一致性维护成本。

运行 ``flow-db apply`` 同步到数据库。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.mysql import (
    BIGINT,
    DATETIME as MySQLDateTime,
    INTEGER,
    MEDIUMTEXT,
    TINYINT,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

# Python-side timestamp 默认值（MySQL 生产使用 server_default；测试 SQLite 使用此 callable）
_utcnow = datetime.utcnow

# 所有 fe_ 业务表共用的 MySQL 表级选项
_FE_TABLE_OPTS: dict[str, str] = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """所有 ORM 模型基类，metadata 驱动 ``create_all`` / ``drop_all``。"""


# ---------------------------------------------------------------------------
# 审计字段 Mixin（每张业务表必须继承）
# ---------------------------------------------------------------------------


class _AuditCols:
    """业务表审计字段；columns 在 DDL 中追加于模型自身字段之后。

    created_at  创建时间（写入后不变）
    updated_at  最后更新时间（ORM update 时由 onupdate 刷新）
    deleted_at  软删除时间戳，NULL 表示未删除
    version     乐观锁版本号，每次 UPDATE 前校验并自增
    created_by  创建人 users.id
    updated_by  最后更新人 users.id
    """

    created_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=False,
        default=_utcnow,
        server_default=text("CURRENT_TIMESTAMP(3)"),
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=False,
        default=_utcnow,
        server_default=text("CURRENT_TIMESTAMP(3)"),
        onupdate=_utcnow,
        comment="最后更新时间",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=True,
        comment="软删除时间，NULL=未删除",
    )
    version: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="乐观锁版本号",
    )
    created_by: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
        comment="创建人 users.id",
    )
    updated_by: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
        comment="最后更新人 users.id",
    )


# ---------------------------------------------------------------------------
# users（已有表，保持向后兼容）
# ---------------------------------------------------------------------------


class User(Base):
    """应用用户；密码仅存哈希，勿存明文。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("1"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ---------------------------------------------------------------------------
# fe_flow  流程主表
# ---------------------------------------------------------------------------


class FeFlow(_AuditCols, Base):
    """流程主表，仅含元数据；body 拆分至 fe_flow_draft / fe_flow_version。

    id           自增主键
    flow_code    业务唯一码（原 flow_id 语义），子表冗余此列以便跨库迁移
    display_name 冗余缓存，save_draft / commit_version 时同步写入，list_flows 无需加载 body
    latest_ver_no 最新已提交版本序号，0 = 仅有草稿
    has_draft    草稿标志位
    """

    __tablename__ = "fe_flow"
    __table_args__ = (
        UniqueConstraint("flow_code", name="uk_fe_flow_code"),
        # WHERE deleted_at IS NULL ORDER BY updated_at DESC（list_flows）
        # IS NULL 定位前缀分区，updated_at 有序消除 filesort
        Index("idx_fe_flow_deleted_at_updated_at", "deleted_at", "updated_at"),
        {**_FE_TABLE_OPTS, "comment": "流程主表，仅元数据，body 拆分至草稿/版本表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    flow_code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="流程业务码，全局唯一，字母/数字/下划线/连字符",
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''"),
        comment="展示名，冗余同步自草稿/最新版本，列表查询无需加载 body",
    )
    latest_ver_no: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="最新已提交版本序号，0=仅有草稿",
    )
    has_draft: Mapped[int] = mapped_column(
        TINYINT(1),
        nullable=False,
        server_default=text("0"),
        comment="是否存在草稿：0=无 1=有",
    )


# ---------------------------------------------------------------------------
# fe_flow_draft  流程草稿（大字段分离）
# ---------------------------------------------------------------------------


class FeFlowDraft(_AuditCols, Base):
    """流程草稿内容表，每个流程唯一一份草稿，大字段从主表分离。

    flow_code  关联 fe_flow.flow_code，用于迁移/按码查询
    body       YAML→JSON 序列化，估算单流程上限 ~3 MB，MEDIUMTEXT 容量 16 MB
    """

    __tablename__ = "fe_flow_draft"
    __table_args__ = (
        UniqueConstraint("flow_code", name="uk_fe_flow_draft_flow_code"),
        {**_FE_TABLE_OPTS, "comment": "流程草稿内容表，大字段从主表分离，1:1 关联 fe_flow"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    flow_code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="关联 fe_flow.flow_code",
    )
    body: Mapped[str] = mapped_column(
        MEDIUMTEXT,
        nullable=False,
        comment="流程定义，YAML→JSON 序列化，最大 16MB",
    )


# ---------------------------------------------------------------------------
# fe_flow_version  流程版本快照（不可变）
# ---------------------------------------------------------------------------


class FeFlowVersion(_AuditCols, Base):
    """流程版本快照表，写入后业务内容不可变。

    flow_code  关联 fe_flow.flow_code
    ver_no     版本业务序号，从 1 单调递增（区别于乐观锁 version 字段）
    body       版本快照，写入后不修改
    """

    __tablename__ = "fe_flow_version"
    __table_args__ = (
        UniqueConstraint("flow_code", "ver_no", name="uk_fe_flow_version_flow_code_ver"),
        # 前缀 (flow_code) 覆盖 list_versions；全键精确 read_version
        {**_FE_TABLE_OPTS, "comment": "流程版本快照表，写入后内容不可变"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    flow_code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="关联 fe_flow.flow_code",
    )
    ver_no: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        comment="版本业务序号，从 1 单调递增（区别于乐观锁 version 字段）",
    )
    body: Mapped[str] = mapped_column(
        MEDIUMTEXT,
        nullable=False,
        comment="版本快照，YAML→JSON，写入后不可修改",
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''"),
        comment="提交时从 body.display_name 提取，用于版本列表展示",
    )
    description: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        server_default=text("''"),
        comment="版本提交说明",
    )


# ---------------------------------------------------------------------------
# fe_env_profile  运行环境配置
# ---------------------------------------------------------------------------


class FeEnvProfile(_AuditCols, Base):
    """运行环境表，取代旧单例 fe_profile_config；每行一个环境（default/sit/prod 等）。

    id            自增主键
    profile_code  业务唯一环境编码（原 profile_id 语义），子表冗余此列以便跨库迁移
    is_default    全局唯一默认环境标志，应用层保证只有一行为 1
    """

    __tablename__ = "fe_env_profile"
    __table_args__ = (
        UniqueConstraint("profile_code", name="uk_fe_env_profile_code"),
        # is_default 基数=2，禁止单独建索引；全表 ≤10 行，list/get_default 全表扫描微秒级
        {**_FE_TABLE_OPTS, "comment": "运行环境表，取代旧单例 fe_profile_config，每行一个环境"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    profile_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="环境编码，如 default / sit / prod",
    )
    display_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="展示名",
    )
    is_default: Mapped[int] = mapped_column(
        TINYINT(1),
        nullable=False,
        server_default=text("0"),
        comment="是否默认环境：0=否 1=是，应用层保证全局唯一一行为 1",
    )
    # JSON shape (recommended): {"debug": [...], "shadow": [...], "production": [...]}
    # Backward compatible: a legacy list[rule] may be stored; server normalizes on write.
    system_capability_policy: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="环境级系统 CapabilityPolicy JSON：按 run_mode 分组（debug/shadow/production）"
                "存 CapabilityRule 列表；优先级低于 deployment_capability_policy，"
                "高于 RunMode 硬编码默认。可为空 {} 或各列表为空。",
    )


# ---------------------------------------------------------------------------
# fe_dict_module  数据字典模块
# ---------------------------------------------------------------------------


class FeDictModule(_AuditCols, Base):
    """数据字典模块表，base/profile 双层叠加。

    layer               'base' | 'profile'
    profile_code    关联fe_env_profile.profile_code
    module_code         点分路径，如 core / app.config.db

    UNIQUE (layer, profile_code, module_code)：
      - base 层 profile_code=default，UNIQUE 可正常约束（非 NULL，确定值）
      - profile 层 profile_code=其他，同样约束
    ⚠ 软删后重建同名模块触发 UNIQUE 冲突：应用层先硬删软删记录再插入。
    """

    __tablename__ = "fe_dict_module"
    __table_args__ = (
        # 前缀 (layer, profile_code) 覆盖 list_modules，第 3 列 module_code 有序无 filesort
        # 全键精确命中 read_module / write_module
        UniqueConstraint(
            "layer", "profile_code", "module_code",
            name="uk_fe_dict_module_layer_profile_code",
        ),
        {**_FE_TABLE_OPTS, "comment": "数据字典模块表，base/profile 双层，base 层 profile_code=default（哨兵值）"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    layer: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'base'"),
        comment="字典层：base=基础层 profile=环境覆盖层",
    )
    profile_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="关联fe_env_profile.profile_code",
    )
    module_code: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''"),
        comment="模块编码，点分路径，如 core / app.config.db",
    )
    yaml_text: Mapped[str] = mapped_column(
        MEDIUMTEXT,
        nullable=False,
        comment="模块 YAML 内容，平均 < 10KB",
    )


# ---------------------------------------------------------------------------
# fe_secret  密钥管理（数据字典密文引用）
# ---------------------------------------------------------------------------


class FeSecret(_AuditCols, Base):
    """密钥定义表；数据字典中 ``secret://<name>`` 引用本表（按 profile 隔离）。

    profile_code  关联 fe_env_profile.profile_code
    secret_name   同一 profile 内唯一
    secret_type   加解密后端类型（如 local_fernet），由 registry 路由
    secret_data   后端相关的密文 JSON（如 ciphertext、nonce 等）
    """

    __tablename__ = "fe_secret"
    __table_args__ = (
        UniqueConstraint(
            "profile_code", "secret_name",
            name="uk_fe_secret_profile_name",
        ),
        {**_FE_TABLE_OPTS, "comment": "密钥管理：按 profile 隔离，名称+类型+密文 JSON"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    profile_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="关联 fe_env_profile.profile_code",
    )
    secret_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="密钥名，与数据字典 secret:// 引用一致",
    )
    secret_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="加解密方案类型，路由到 SecretCryptoBackend",
    )
    secret_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="方案相关的密文/元数据 JSON",
    )


# ---------------------------------------------------------------------------
# fe_lookup_ns  Lookup 命名空间（Schema 定义）
# ---------------------------------------------------------------------------


class FeLookupNs(_AuditCols, Base):
    """Lookup 命名空间表，存储 Schema 定义；行数据在 fe_lookup_row。

    profile_code    关联fe_env_profile.profile_code
    ns_code          命名空间编码

    uk (profile_code, ns_code)：业务全局唯一，便于迁移/按码引用
    """

    __tablename__ = "fe_lookup_ns"
    __table_args__ = (
        UniqueConstraint(
            "profile_code", "ns_code",
            name="uk_fe_lookup_ns_env_code_ns",
        ),
        {**_FE_TABLE_OPTS, "comment": "Lookup 命名空间表，含 Schema 定义，行数据在 fe_lookup_row"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    profile_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="关联fe_env_profile.profile_code",
    )
    ns_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="命名空间编码，如 country_code / product_type",
    )
    schema_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="JSON Schema 定义，描述 row_data 字段结构，通常 < 10KB",
    )


# ---------------------------------------------------------------------------
# fe_lookup_row  Lookup 行数据
# ---------------------------------------------------------------------------


class FeLookupRow(_AuditCols, Base):
    """Lookup 行数据表。

    profile_code   关联fe_lookup_ns.profile_code
    ns_code        关联fe_lookup_ns.ns_code
    row_data       单行数据，字段与 schema_json 对应

    idx_fe_lookup_row_profile_ns_deleted_at (profile_code, ns_code, deleted_at)：
      按业务码查行
    ⚠ put_table 反复导入会积累软删历史行，建议定期清理 deleted_at IS NOT NULL 的行。
    """

    __tablename__ = "fe_lookup_row"
    __table_args__ = (
        Index(
            "idx_fe_lookup_row_profile_ns_deleted_at",
            "profile_code",
            "ns_code",
            "deleted_at",
        ),
        {**_FE_TABLE_OPTS, "comment": "Lookup 行数据表，每行一条参考数据，ORDER BY id 保持插入顺序"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键，ORDER BY id 保证插入顺序即业务顺序",
    )
    profile_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="关联fe_lookup_ns.profile_code",
    )
    ns_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="关联fe_lookup_ns.ns_code",
    )
    row_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment='单行数据 {"field": value}，字段与 schema_json 对应',
    )


# ---------------------------------------------------------------------------
# fe_user_script  用户 Starlark 脚本
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# fe_flow_deployment  流程部署配置（运行调度层）
# ---------------------------------------------------------------------------


class FeFlowDeployment(_AuditCols, Base):
    """流程部署配置：将 (flow_code, ver_no) 与运行模式 / 调度规则 / Worker 策略 / 能力策略绑定。

    schedule_type:
        once     一次性触发（执行一次后 stopped）
        cron     按 cron 表达式周期触发（每次在 fe_deploy_run 插入一条 queued 记录）
        resident 常驻流程（带重启 backoff）

    schedule_config:
        once:    {}
        cron:    {"cron_expr": "0 8 * * *"}
        resident:{}（无额外配置）

    worker_policy:
        type:                "multi_active" | "single_active"
        min_workers:         至少分配的 worker 数（multi_active 控制副本数；single_active 控制候选）
        max_restarts:        resident 崩溃最大重启次数，默认 5
        restart_backoff_s:   重启退避基础秒数；实际 = base * 2^(attempt-1)

    capability_policy: list[CapabilityRule]，可空 list；JSON 持久化。
    """

    __tablename__ = "fe_flow_deployment"
    __table_args__ = (
        Index("idx_fe_flow_deployment_status", "status"),
        Index("idx_fe_flow_deployment_flow_code", "flow_code"),
        {**_FE_TABLE_OPTS, "comment": "流程部署配置表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    flow_code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="关联 fe_flow.flow_code",
    )
    ver_no: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        comment="部署使用的版本号（fe_flow_version.ver_no）",
    )
    mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'production'"),
        comment="RunMode：debug / shadow / production",
    )
    schedule_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'once'"),
        comment="调度类型：once / cron / resident",
    )
    schedule_config: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="调度配置 JSON；once={} / cron={cron_expr} / resident={}",
    )
    worker_policy: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="Worker 分配策略 JSON",
    )
    capability_policy: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        comment="Deployment 级 CapabilityRule 列表 JSON；可为空 []",
    )
    worker_targeting: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment=(
            "Worker 定向策略 JSON。推荐结构："
            '{"mode":"any"} / {"mode":"pin","worker_id":"..."} / {"mode":"pool","worker_ids":["..."]}；'
            "空对象等价于 any"
        ),
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'pending'"),
        comment="状态：pending / running / stopping / stopped / failed",
    )
    status_detail: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="状态诊断信息 JSON（失败原因、最近一次异常等）",
    )
    env_profile_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="运行 profile（数据字典 / lookup namespace 解析使用）",
    )
    parent_deployment_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
        comment="已废弃：历史数据可能为旧版 cron 克隆子部署；新代码勿写入",
    )
    observability: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment=(
            "可观测策略 JSON，结构："
            '{"log_level":"ERROR","span_retention_days":3,"span_nodes":{'
            '"__default__":{"rate":1.0},'
            '"<node_id>":{"rate":0.05,"always_on_failure":true,"scope_key":"$.alert.id"}}}; '
            "空 {} 等价于全部 __default__ 配置，log_level=ERROR"
        ),
    )


# ---------------------------------------------------------------------------
# fe_worker  Worker 进程注册表
# ---------------------------------------------------------------------------


class FeWorker(_AuditCols, Base):
    """Worker 进程注册表。

    last_heartbeat 由 Worker 进程每 10s 更新；Coordinator 视 30s 未更新为死亡。
    """

    __tablename__ = "fe_worker"
    __table_args__ = (
        UniqueConstraint("worker_id", name="uk_fe_worker_worker_id"),
        Index("idx_fe_worker_status_heartbeat", "status", "last_heartbeat"),
        {**_FE_TABLE_OPTS, "comment": "Worker 注册表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    worker_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="Worker 业务唯一码（UUID）",
    )
    host: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''"),
        comment="Worker 主机名 / IP",
    )
    pid: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="进程 PID",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'active'"),
        comment="状态：active / idle / dead",
    )
    last_heartbeat: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=False,
        default=_utcnow,
        server_default=text("CURRENT_TIMESTAMP(3)"),
        comment="最后心跳时间",
    )
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment='Worker 能力 JSON，如 {"max_concurrent_flows": 8}',
    )


# ---------------------------------------------------------------------------
# fe_worker_assignment  Worker 任务分配表
# ---------------------------------------------------------------------------


class FeWorkerAssignment(_AuditCols, Base):
    """Coordinator 将 Deployment 分配给 Worker 的物化记录。

    role:
        leader   single_active 模式下唯一执行者，lease_expires_at 续约
        standby  single_active 模式下候选；leader 死亡时晋升
        replica  multi_active 模式下并发副本之一

    UK (deployment_id, worker_id)：同 worker 同 deployment 仅有一条活跃记录；
    软删后 deleted_at 不为 NULL，UK 仍生效（同名重建需先硬删软删行）。
    """

    __tablename__ = "fe_worker_assignment"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "worker_id",
            name="uk_fe_worker_assignment_dep_worker",
        ),
        Index("idx_fe_worker_assignment_worker_id", "worker_id"),
        Index("idx_fe_worker_assignment_deployment_id", "deployment_id"),
        {**_FE_TABLE_OPTS, "comment": "Worker 任务分配表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    deployment_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        nullable=False,
        comment="关联 fe_flow_deployment.id",
    )
    worker_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="关联 fe_worker.worker_id",
    )
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'replica'"),
        comment="角色：leader / standby / replica",
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=True,
        comment="leader 租约到期时间；非 leader 为 NULL",
    )

#
# ---------------------------------------------------------------------------
# fe_deploy_run  部署运行实例（运行中心专用）
# ---------------------------------------------------------------------------
#


class FeDeployRun(_AuditCols, Base):
    """部署运行实例（Execution / Instance）。

    与测试运行完全隔离：只用于部署/调度产生的运行实例。
    可观测数据已下沉到 ``fe_run_span`` / ``fe_node_metric``；本表仅保留运行
    生命周期与计数指针，避免 MEDIUMTEXT blob 进入主表。
    """

    __tablename__ = "fe_deploy_run"
    __table_args__ = (
        Index("idx_fe_deploy_run_deployment_id", "deployment_id"),
        Index("idx_fe_deploy_run_deployment_id_status", "deployment_id", "status"),
        Index("idx_fe_deploy_run_flow_code_started_at", "flow_code", "started_at"),
        Index("idx_fe_deploy_run_worker_id_started_at", "worker_id", "started_at"),
        {**_FE_TABLE_OPTS, "comment": "部署运行实例表（运行中心专用）"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    deployment_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        nullable=False,
        comment="关联 fe_flow_deployment.id",
    )
    worker_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="执行 worker 的 worker_id；调度中/未分配时可为空",
    )
    flow_code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="流程业务码",
    )
    ver_no: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        comment="流程版本号",
    )
    mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'production'"),
        comment="部署模式：shadow / production",
    )
    schedule_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'once'"),
        comment="触发方式：once / cron / resident",
    )
    trigger_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'manual'"),
        comment="触发来源：manual / cron / resident_restart / unknown",
    )
    trigger_context: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="触发上下文（可选），用于诊断/回放；resident 可为空",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'running'"),
        comment="状态：queued / running / completed / failed / terminated",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=True,
        comment="执行开始时间；queued 时为 NULL，claim 后写入",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=True,
        comment="结束时间；运行中为 NULL",
    )
    span_count: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
        comment="本次运行内观察到的 Span 总数（含未采样）；详情见 fe_run_span",
    )
    sampled_span_count: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
        comment="实际写入 fe_run_span 的 Span 数（采样后）",
    )
    error: Mapped[str | None] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        comment="失败 / 终止时的错误信息（不再保存 flow_logs / global_ns / node blob）",
    )


#
# ---------------------------------------------------------------------------
# fe_test_run  测试用例运行（测试中心专用）
# ---------------------------------------------------------------------------
#


class FeTestRun(_AuditCols, Base):
    """测试用例运行实例（per-case run）。

    与部署运行完全隔离：只用于测试批次（test batch）内的用例运行。
    """

    __tablename__ = "fe_test_run"
    __table_args__ = (
        Index("idx_fe_test_run_batch_id", "test_batch_id"),
        Index("idx_fe_test_run_flow_code_started_at", "flow_code", "started_at"),
        {**_FE_TABLE_OPTS, "comment": "测试用例运行表（测试中心专用）"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    test_batch_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        nullable=False,
        comment="关联 fe_flow_test_batch.id",
    )
    worker_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="执行 worker 的 worker_id（如测试也走 worker）；当前实现可为空",
    )
    flow_code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="流程业务码",
    )
    ver_no: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        comment="流程版本号",
    )
    mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'debug'"),
        comment="测试运行模式：debug（固定）",
    )
    case_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''"),
        comment="用例键（用于对齐对比/定位）",
    )
    case_index: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="批次内序号（1..N）；0 表示未知/未计算",
    )
    trigger_context: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="用例触发上下文（含 row 等）",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'running'"),
        comment="状态：running / completed / failed / terminated",
    )
    started_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=False,
        default=_utcnow,
        server_default=text("CURRENT_TIMESTAMP(3)"),
        comment="开始时间",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=True,
        comment="结束时间；运行中为 NULL",
    )
    error: Mapped[str | None] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        comment="失败 / 终止时的错误信息（详细执行记录见 fe_run_span）",
    )
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="测试断言评估结果：verdict / rules 等（JSON）",
    )


# ---------------------------------------------------------------------------
# fe_flow_run  (REMOVED) — 历史 legacy 表，统一迁移至 fe_deploy_run / fe_test_run
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# fe_flow_test_batch  测试批次聚合表
# ---------------------------------------------------------------------------


class FeFlowTestBatch(_AuditCols, Base):
    """以 lookup namespace 行作为测试集的批次聚合表。

    每行 lookup namespace 数据 → 一次 fe_test_run；
    本表持有汇总（total / completed / error）。
    若由测试方案触发，plan_id / plan_snapshot 记录来源与运行时刻快照（ad-hoc 批次为 NULL）。
    """

    __tablename__ = "fe_flow_test_batch"
    __table_args__ = (
        Index("idx_fe_flow_test_batch_flow_code", "flow_code"),
        Index("idx_fe_flow_test_batch_plan_id", "plan_id"),
        {**_FE_TABLE_OPTS, "comment": "测试批次聚合表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    flow_code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="流程业务码",
    )
    ver_no: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        comment="流程版本号",
    )
    test_ns_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="测试集 lookup namespace 编码",
    )
    profile_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="测试集所属 profile",
    )
    mock_config: Mapped[str] = mapped_column(
        MEDIUMTEXT,
        nullable=False,
        comment="dict[node_id, MockConfig] JSON 序列化",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'pending'"),
        comment="状态：pending / running / completed / failed",
    )
    started_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=False,
        default=_utcnow,
        server_default=text("CURRENT_TIMESTAMP(3)"),
        comment="开始时间",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=True,
        comment="结束时间；运行中为 NULL",
    )
    total_runs: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="总运行数 = 测试集行数",
    )
    completed_runs: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="成功运行数",
    )
    error_runs: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="失败运行数",
    )
    plan_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
        comment="来源 fe_flow_test_plan.id；ad-hoc 批次为 NULL",
    )
    plan_snapshot: Mapped[str | None] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        comment="运行时刻的方案快照 JSON（含解析后的 ver_no 等）；ad-hoc 为 NULL",
    )


# ---------------------------------------------------------------------------
# fe_flow_test_plan  测试方案（可独立维护，多次运行）
# ---------------------------------------------------------------------------


class FeFlowTestPlan(_AuditCols, Base):
    """测试方案定义表（Plan）：

    将「流程版本选择 + 测试集 + profile + 并发 + mock + 上下文映射」固化为可复用资源；
    每次运行方案会生成一个独立的 fe_flow_test_batch（Run），并在 batch 行记录 plan 快照。
    """

    __tablename__ = "fe_flow_test_plan"
    __table_args__ = (
        Index("idx_fe_flow_test_plan_flow_code", "flow_code"),
        {**_FE_TABLE_OPTS, "comment": "测试方案定义表，可复用、多次运行"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''"),
        comment="方案名称（展示）",
    )
    flow_code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="流程业务码",
    )
    # latest / draft / vN / N
    version_channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'latest'"),
        comment="版本选择通道：latest/draft/vN/N",
    )
    test_ns_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="测试集 lookup namespace 编码",
    )
    profile_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("''"),
        comment="运行 profile（数据字典/lookup 解析使用）",
    )
    concurrency: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("4"),
        comment="并发度",
    )
    mock_config: Mapped[str] = mapped_column(
        MEDIUMTEXT,
        nullable=False,
        comment="dict[node_id, MockConfig] JSON 序列化",
    )
    context_mapping: Mapped[str] = mapped_column(
        MEDIUMTEXT,
        nullable=False,
        comment="lookup row → context 映射 JSON（dict）序列化",
    )
    assertions: Mapped[str] = mapped_column(
        MEDIUMTEXT,
        nullable=False,
        comment="断言规则 JSON 数组（与 mock_config 并列）",
    )
    capability_policy: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="计划级 CapabilityRule 列表 JSON；批次创建时若未显式传入则继承该值。可为空 []",
    )


# ---------------------------------------------------------------------------
# fe_user_script  用户 Starlark 脚本
# ---------------------------------------------------------------------------


class FeUserScript(_AuditCols, Base):
    """用户 Starlark 脚本存储表。

    uk_fe_user_script_tenant_path (tenant, rel_path)：
      覆盖索引：SELECT tenant, rel_path WHERE deleted_at IS NULL ORDER BY tenant, rel_path
        → 两列均在索引内，有序，无 filesort，无回表（deleted_at 过滤可接受）
    """

    __tablename__ = "fe_user_script"
    __table_args__ = (
        UniqueConstraint("tenant", "rel_path", name="uk_fe_user_script_tenant_path"),
        {**_FE_TABLE_OPTS, "comment": "用户 Starlark 脚本存储表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    tenant: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="租户/命名空间，对应 user://<tenant>/ 路径段",
    )
    rel_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        server_default=text("''"),
        comment="相对路径，如 my_lib/utils.star，格式由应用层校验",
    )
    content: Mapped[str] = mapped_column(
        MEDIUMTEXT,
        nullable=False,
        comment="Starlark 源码，单文件 50-200 行",
    )
    description: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="脚本说明，供能力与脚本页展示",
    )
    export_functions: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="导出符号列表（顶层 def 名），保存时从源码提取",
    )


# ---------------------------------------------------------------------------
# fe_run_span  通用执行 Span（覆盖 deploy/test 域）
# ---------------------------------------------------------------------------


class FeRunSpan(_AuditCols, Base):
    """统一的执行 Span 表，承载所有可观测的「执行单元」。

    Span 是 OpenTelemetry 风格的执行边界记录：
      - node_type=task:       TaskNode 执行（默认不采，仅按配置开启）
      - node_type=loop_iter:  LoopNode 单次迭代
      - node_type=subflow:    SubflowNode 单次调用

    历史上还存在 node_type=flow_root（once/cron/test 的合成顶层节点），
    现已废弃：流程级运行由 fe_deploy_run / fe_test_run 承载，无需为它
    再合成一个 Span。read 路径在 ``list_spans_forest`` 中过滤掉该类型
    以兼容存量数据。

    通过 ``parent_span_id`` 形成树（嵌套循环 / 嵌套子流程自然支持）。
    多循环场景由 ``node_id`` 区分，无需新表。

    `deploy_run_id` / `test_run_id` 二选一非空：

      - 部署运行（once / cron / resident）→ deploy_run_id 非空
      - 测试运行 → test_run_id 非空

    JSON 字段语义：

      child_spans  直接子节点摘要（不递归），列表元素：
                   {node_id, node_name, duration_ms, status, error?}
      logs         Span 期间收集到的日志条目（按级别过滤），列表元素：
                   {level, msg, source, t_ms}
      attributes   用户自定义 KV（业务标签 / 链路追踪 ID 等扩展点）
    """

    __tablename__ = "fe_run_span"
    __table_args__ = (
        # 按节点翻页（结果列表的主索引）
        Index(
            "idx_fe_run_span_deploy_run_node_started",
            "deploy_run_id",
            "node_id",
            "started_at",
        ),
        # 失败定位
        Index(
            "idx_fe_run_span_deploy_run_status_started",
            "deploy_run_id",
            "status",
            "started_at",
        ),
        # 测试域查询
        Index(
            "idx_fe_run_span_test_run_node_started",
            "test_run_id",
            "node_id",
            "started_at",
        ),
        # 按业务键检索（scope_key 前缀索引 64 字符足够区分百万级告警 ID）
        Index(
            "idx_fe_run_span_scope_key_started",
            "scope_key",
            "started_at",
        ),
        # 父子树导航
        Index("idx_fe_run_span_parent", "parent_span_id"),
        # 跨 run 统计
        Index(
            "idx_fe_run_span_flow_code_started",
            "flow_code",
            "started_at",
        ),
        {**_FE_TABLE_OPTS, "comment": "通用执行 Span 表（可观测中枢）"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    deploy_run_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
        comment="部署运行 ID（fe_deploy_run.id）；测试运行为 NULL",
    )
    test_run_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
        comment="测试运行 ID（fe_test_run.id）；部署运行为 NULL",
    )
    flow_code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="流程业务码（冗余，便于跨 run 检索）",
    )
    node_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="产生 Span 的节点 id（历史 flow_root 行用 '__flow_root__'，已废弃）",
    )
    node_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'task'"),
        comment="Span 类型：task / loop_iter / subflow（历史值 flow_root 已废弃）",
    )
    span_seq: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="(run_id, node_id) 内单调递增序号，便于按发生顺序排序",
    )
    parent_span_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
        comment="父 Span id（嵌套循环 / 嵌套子流程）；顶层为 NULL",
    )
    scope_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        server_default=text("''"),
        comment="业务键（由 observability.span_nodes.<id>.scope_key 配置提取，可为空）",
    )
    started_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=False,
        default=_utcnow,
        comment="Span 开始时间",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=True,
        comment="Span 结束时间；未完成时为 NULL（异常落库才出现）",
    )
    duration_ms: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        nullable=True,
        comment="Span 耗时（毫秒），冗余字段便于查询",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'running'"),
        comment="状态：success / failed / skipped / running",
    )
    error: Mapped[str | None] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        comment="失败原因（仅 status=failed 时有意义）",
    )
    child_spans: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="直接子节点摘要 JSON 列表：[{node_id, node_name, duration_ms, status, error?}]",
    )
    logs: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Span 内日志条目 JSON 列表：[{level, msg, source, t_ms}]",
    )
    attributes: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="用户自定义 KV 扩展点 JSON",
    )
    sampled: Mapped[int] = mapped_column(
        TINYINT(1),
        nullable=False,
        server_default=text("1"),
        comment="1=主动采样命中；0=always_on_failure 触发回补",
    )


# ---------------------------------------------------------------------------
# fe_node_metric  节点级时序聚合（5 分钟桶）
# ---------------------------------------------------------------------------


class FeNodeMetric(_AuditCols, Base):
    """节点级时序聚合表。

    与 ``fe_run_span`` 互补：Metric 是「始终在线」的聚合视图（永久保留），
    Span 是「按需采样」的执行快照（短期保留）。每个 (deploy_run_id, node_id,
    bucket_at) 唯一一行，由 Worker 后台 ``_obs_flush_loop`` 周期性 UPSERT。

    百分位由 backend 在内存中（循环缓冲 tail-1000）计算后写入；新 bucket
    出现时上一个桶被 finalize。
    """

    __tablename__ = "fe_node_metric"
    __table_args__ = (
        UniqueConstraint(
            "deploy_run_id",
            "node_id",
            "bucket_at",
            name="uk_fe_node_metric_run_node_bucket",
        ),
        # 跨 run 长期趋势（flow_code, node_id）
        Index(
            "idx_fe_node_metric_flow_node_bucket",
            "flow_code",
            "node_id",
            "bucket_at",
        ),
        {**_FE_TABLE_OPTS, "comment": "节点级时序聚合表（5 分钟桶）"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    deploy_run_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        nullable=False,
        comment="关联 fe_deploy_run.id",
    )
    flow_code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="流程业务码（冗余，便于跨 run 长期趋势）",
    )
    node_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default=text("''"),
        comment="节点 id（流程级指标使用历史标签 '__flow_root__'）",
    )
    bucket_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=False,
        comment="5 分钟时间桶起点（向下取整 UTC）",
    )
    span_count: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="桶内 Span 数量",
    )
    success_count: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="成功数",
    )
    failed_count: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="失败数",
    )
    skipped_count: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="跳过数",
    )
    total_ms: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        nullable=False,
        server_default=text("0"),
        comment="耗时累加（仅 success/failed 计入，便于计算 avg）",
    )
    p50_ms: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        nullable=True,
        comment="P50（tail-1000 样本）",
    )
    p95_ms: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        nullable=True,
        comment="P95",
    )
    p99_ms: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        nullable=True,
        comment="P99",
    )
    max_ms: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        nullable=True,
        comment="桶内最大耗时",
    )
    min_ms: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        nullable=True,
        comment="桶内最小耗时",
    )
