import pytest

from sophys.cli.core import get_cli_envvar, ENVVARS, KAFKA_HOST_ENVVAR, KAFKA_PORT_ENVVAR, KAFKA_TOPIC_ENVVAR, CLI_KAFKA_HOST_ADDRESS_DEF, CLI_KAFKA_PORT_ADDRESS_DEF, CLI_KAFKA_TOPIC_NAME_DEF


@pytest.fixture
def set_environment(monkeypatch):
    monkeypatch.setenv(KAFKA_HOST_ENVVAR, "my_cool_host")
    monkeypatch.setenv(KAFKA_PORT_ENVVAR, "1234")
    monkeypatch.setenv(KAFKA_TOPIC_ENVVAR, "my_cool_topic")


@pytest.fixture
def empty_environment(monkeypatch):
    monkeypatch.delenv(KAFKA_HOST_ENVVAR, raising=False)
    monkeypatch.delenv(KAFKA_PORT_ENVVAR, raising=False)
    monkeypatch.delenv(KAFKA_TOPIC_ENVVAR, raising=False)


def test_get_cli_envvar_set_value(set_environment):
    assert get_cli_envvar(KAFKA_HOST_ENVVAR) == "my_cool_host"
    assert get_cli_envvar(KAFKA_PORT_ENVVAR) == "1234"
    assert get_cli_envvar(KAFKA_TOPIC_ENVVAR) == "my_cool_topic"


def test_get_cli_envvar_default(empty_environment):
    assert get_cli_envvar(KAFKA_HOST_ENVVAR) == CLI_KAFKA_HOST_ADDRESS_DEF
    assert get_cli_envvar(KAFKA_PORT_ENVVAR) == CLI_KAFKA_PORT_ADDRESS_DEF
    assert get_cli_envvar(KAFKA_TOPIC_ENVVAR) == CLI_KAFKA_TOPIC_NAME_DEF


def test_get_cli_envvar_wrong_variable():
    assert get_cli_envvar("unexisting_variable") == "NO_DEFAULT"


def test_envvars_get_correct_value(set_environment):
    assert ENVVARS.KAFKA_HOST == "my_cool_host"
    assert ENVVARS.KAFKA_PORT == "1234"
    assert ENVVARS.KAFKA_TOPIC == "my_cool_topic"


def test_envvars_get_default_value(empty_environment):
    assert ENVVARS.KAFKA_HOST == CLI_KAFKA_HOST_ADDRESS_DEF
    assert ENVVARS.KAFKA_PORT == CLI_KAFKA_PORT_ADDRESS_DEF
    assert ENVVARS.KAFKA_TOPIC == CLI_KAFKA_TOPIC_NAME_DEF


def test_envvars_get_wrong_variable():
    assert ENVVARS.unexisting_variable == "NO_DEFAULT"
