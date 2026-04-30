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
        cron     按 cron 表达式周期触发（每次产生一个 once 子部署）
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
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'pending'"),
        comment="状态：pending / running / stopping / stopped / failed",
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
        comment="cron 触发时填父 deployment.id；其他场景 NULL",
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


# ---------------------------------------------------------------------------
# fe_flow_run  流程运行记录表
# ---------------------------------------------------------------------------


class FeFlowRun(_AuditCols, Base):
    """单次流程运行记录。

    deployment_id 与 test_batch_id 互斥（生产 vs 测试）：
        生产运行（once/cron/resident）：deployment_id 非空，test_batch_id 为空
        测试运行：                       test_batch_id 非空，deployment_id 为空

    node_runs 与 node_stats 互斥：
        once/cron/test → node_runs（list[NodeRunInfo.to_dict()] 序列化）
        resident       → node_stats（聚合统计 JSON），同时 iteration_count 累计
    """

    __tablename__ = "fe_flow_run"
    __table_args__ = (
        Index("idx_fe_flow_run_deployment_id", "deployment_id"),
        Index("idx_fe_flow_run_test_batch_id", "test_batch_id"),
        Index(
            "idx_fe_flow_run_flow_code_started_at",
            "flow_code",
            "started_at",
        ),
        {**_FE_TABLE_OPTS, "comment": "流程运行记录表"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    deployment_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
        comment="生产运行关联 fe_flow_deployment.id；测试运行为 NULL",
    )
    test_batch_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
        comment="测试运行关联 fe_flow_test_batch.id；生产运行为 NULL",
    )
    worker_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="执行 worker 的 worker_id；测试可为空",
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
        comment="RunMode：debug / shadow / production",
    )
    trigger_context: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="触发时的初始 context；resident 流程为 NULL",
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
    iteration_count: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        nullable=True,
        comment="resident 累计迭代次数；非 resident 为 NULL",
    )
    node_runs: Mapped[str | None] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        comment="非 resident：list[NodeRunInfo.to_dict()] 的 JSON",
    )
    node_stats: Mapped[str | None] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        comment="resident：节点级聚合统计 JSON",
    )
    flow_logs: Mapped[str | None] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        comment="flow-level hook 日志 JSON",
    )
    error: Mapped[str | None] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        comment="失败 / 终止时的错误信息",
    )


# ---------------------------------------------------------------------------
# fe_flow_test_batch  测试批次聚合表
# ---------------------------------------------------------------------------


class FeFlowTestBatch(_AuditCols, Base):
    """以 lookup namespace 行作为测试集的批次聚合表。

    每行 lookup namespace 数据 → 一次 RunMode.DEBUG 流程运行 → 一条 fe_flow_run；
    本表持有汇总（total / completed / error）。
    """

    __tablename__ = "fe_flow_test_batch"
    __table_args__ = (
        Index("idx_fe_flow_test_batch_flow_code", "flow_code"),
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
