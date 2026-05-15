"""Tests for secret management and local_fernet crypto."""

from __future__ import annotations

import os

import pytest

from flow_engine.secrets.errors import SecretError
from flow_engine.secrets.reference import is_secret_reference, parse_secret_reference
from flow_engine.secrets.service import (
    decrypt_secret_by_name,
    encrypt_plaintext,
    resolve_secret_value,
)
from flow_engine.stores import data_dict
from flow_engine.stores.profile_store import profile_scope, store as profile_store
from flow_engine.stores.secret_store import SecretStoreError, store as secret_store


@pytest.fixture
def master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from cryptography.fernet import Fernet

    monkeypatch.setenv("FLOW_SECRET_MASTER_KEY", Fernet.generate_key().decode("ascii"))


def test_secret_reference_parse() -> None:
    assert is_secret_reference("secret://es_password")
    assert parse_secret_reference("secret://es_password") == "es_password"
    with pytest.raises(SecretError):
        parse_secret_reference("secret es")


def test_local_fernet_roundtrip(master_key: None) -> None:
    data = encrypt_plaintext("local_fernet", "my-kafka-password")
    plain = resolve_secret_value("x")  # not a ref — pass-through
    assert plain == "x"
    secret_store().put_secret("kafka_pwd", "local_fernet", data, profile="default")
    with profile_scope("default"):
        assert decrypt_secret_by_name("kafka_pwd") == "my-kafka-password"
        assert resolve_secret_value("secret://kafka_pwd") == "my-kafka-password"


def test_secrets_isolated_by_profile(master_key: None) -> None:
    profile_store().create_profile("sit")
    data_default = encrypt_plaintext("local_fernet", "default-pwd")
    data_sit = encrypt_plaintext("local_fernet", "sit-pwd")
    secret_store().put_secret("es_pwd", "local_fernet", data_default, profile="default")
    secret_store().put_secret("es_pwd", "local_fernet", data_sit, profile="sit")

    with profile_scope("default"):
        assert decrypt_secret_by_name("es_pwd") == "default-pwd"
    with profile_scope("sit"):
        assert decrypt_secret_by_name("es_pwd") == "sit-pwd"


def test_dictionary_keeps_secret_references_at_runtime(master_key: None) -> None:
    """Flow runtime must not auto-decrypt; integration code decrypts in Python."""
    data = encrypt_plaintext("local_fernet", "es-secret")
    secret_store().put_secret("es_pwd", "local_fernet", data, profile="default")
    st = data_dict.store()
    st.write_module(
        "base",
        "middleware.elasticsearch",
        "hosts:\n  - localhost:9200\npassword: secret://es_pwd\n",
    )
    tree = data_dict.tree_copy("default")
    assert tree["middleware"]["elasticsearch"]["password"] == "secret://es_pwd"


def test_missing_secret_in_profile_raises(master_key: None) -> None:
    profile_store().create_profile("prod")
    with profile_scope("prod"):
        with pytest.raises(SecretStoreError, match="not found"):
            decrypt_secret_by_name("missing")


def test_missing_master_key_raises() -> None:
    os.environ.pop("FLOW_SECRET_MASTER_KEY", None)
    with pytest.raises(SecretError, match="FLOW_SECRET_MASTER_KEY"):
        encrypt_plaintext("local_fernet", "x")
