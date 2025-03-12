import pytest

import typing

from sophys.cli.core.magics import NamespaceKeys, get_from_namespace, add_to_namespace
from sophys.cli.core.base_configuration import create_bec, create_callbacks, create_run_engine, create_kafka_parameters


def test_create_bec():
    _globals = {}

    from bluesky.callbacks.best_effort import BestEffortCallback
    BEC, BEC_callback = create_bec(_globals)

    assert not BEC._plots_enabled
    assert get_from_namespace(NamespaceKeys.BEST_EFFORT_CALLBACK, ns=_globals) is BEC
    assert isinstance(BEC, BestEffortCallback)

    assert isinstance(BEC_callback, typing.Callable), type(BEC_callback)


def test_create_callbacks():
    _globals = {}

    db, last_data, bec = create_callbacks(_globals)

    assert get_from_namespace(NamespaceKeys.DATABROKER, ns=_globals) is not None
    assert get_from_namespace(NamespaceKeys.BEST_EFFORT_CALLBACK, ns=_globals) is not None

    db("start", {"uid": "abc", "time": 0})
    db("stop", {"run_start": "abc"})

    assert get_from_namespace(NamespaceKeys.LAST_DATA, ns=_globals) is None
    last_data("stop", {})
    assert get_from_namespace(NamespaceKeys.LAST_DATA, ns=_globals) is not None


def test_create_run_engine():
    _globals = {}

    from bluesky import RunEngine
    RE = create_run_engine(_globals)

    assert get_from_namespace(NamespaceKeys.RUN_ENGINE, ns=_globals) is RE
    assert isinstance(RE, RunEngine)


def test_create_kafka_parameters():
    _globals = {}

    def default_kafka_topics(): return ["skip_bluesky_documents", "not_used"]
    def default_bootstrap_servers(): return ["1.2.3.4:1234", "5.6.7.8:5678"]

    topic_name, bootstrap_servers = create_kafka_parameters(default_kafka_topics, default_bootstrap_servers, "skip", _globals)

    assert topic_name == default_kafka_topics()[0]
    assert bootstrap_servers == default_bootstrap_servers()

    assert get_from_namespace(NamespaceKeys.KAFKA_TOPIC, ns=_globals) == topic_name
    assert get_from_namespace(NamespaceKeys.KAFKA_BOOTSTRAP, ns=_globals) == bootstrap_servers

    add_to_namespace(NamespaceKeys.TEST_MODE, True, _globals=_globals)
    add_to_namespace(NamespaceKeys.LOCAL_MODE, True, _globals=_globals)

    topic_name, bootstrap_servers = create_kafka_parameters(default_kafka_topics, default_bootstrap_servers, "skip", _globals)

    assert topic_name == default_kafka_topics()[0].replace("skip", "test")
    assert bootstrap_servers == default_bootstrap_servers()

    assert get_from_namespace(NamespaceKeys.KAFKA_TOPIC, ns=_globals) == topic_name
    assert get_from_namespace(NamespaceKeys.KAFKA_BOOTSTRAP, ns=_globals) == bootstrap_servers
