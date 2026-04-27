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
        server_default=text("CURRENT_TIMESTAMP(3)"),
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=3),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
        onupdate=func.now(),
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
