import functools
import logging
import importlib

from types import SimpleNamespace

from kafka.errors import NoBrokersAvailable

from bluesky import RunEngine
from bluesky import plans as bp, plan_stubs as bps
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.utils import RunEngineInterrupted

import databroker

from sophys.common.utils.kafka.monitor import ThreadedMonitor

from sophys.cli.core.magics import NamespaceKeys, add_to_namespace, get_from_namespace


# Appease LSPs and allow some use of the application with no extension.
if "EXTENSION" not in globals():
    EXTENSION = "common"


def create_bec():
    BEC = BestEffortCallback()
    BEC.disable_plots()

    # NOTE: This is like so because otherwise we either have to force a matplotlib backend
    # , or the table printing functionality doesn't work at all in remote settings.
    # FIXME: This impossibilitates using the graphical callbacks. Find out a better way.
    BEC_callback = functools.partial(BEC, escape=True)

    add_to_namespace(NamespaceKeys.BEST_EFFORT_CALLBACK, BEC, _globals=globals())

    return BEC, BEC_callback


def create_callbacks():
    DB = databroker.Broker.named("temp")

    def update_last_data(name, _):
        if name == "stop":
            add_to_namespace(NamespaceKeys.LAST_DATA, DB[-1].table(), _globals=globals())

    BEC, BEC_callback = create_bec()

    return [DB.v1.insert, update_last_data, BEC_callback]


def create_run_engine():
    class RunEngineWithoutTracebackOnPause(RunEngine):
        def interruption_wrapper(func):
            @functools.wraps(func)
            def wrapper(self, *args, **kwargs):
                try:
                    return func(self, *args, **kwargs)
                except RunEngineInterrupted:
                    print(self.pause_msg)
            return wrapper

        @functools.wraps(RunEngine.__call__)
        @interruption_wrapper
        def __call__(self, *args, **kwargs):
            return super().__call__(*args, **kwargs)

        @functools.wraps(RunEngine.resume)
        @interruption_wrapper
        def resume(self, *args, **kwargs):
            return super().resume(*args, **kwargs)

    RE = RunEngineWithoutTracebackOnPause({})
    add_to_namespace(NamespaceKeys.RUN_ENGINE, RE, _globals=globals())

    return RE


def create_kafka_parameters(default_topic_names, default_bootstrap_servers):
    kafka_topic = default_topic_names()[0]
    if get_from_namespace(NamespaceKeys.TEST_MODE, False) and get_from_namespace(NamespaceKeys.LOCAL_MODE, False):
        kafka_topic = kafka_topic.replace(EXTENSION, "test")

    add_to_namespace(NamespaceKeys.KAFKA_TOPIC, kafka_topic, _globals=globals())

    return kafka_topic, default_bootstrap_servers()


def create_kafka_monitor(kafka_topic, bootstrap_servers, callbacks):
    def __create_kafka_monitor(topic_name: str, bootstrap_servers: list[str], subscriptions: list[callable]):
        monitor = ThreadedMonitor(None, [], topic_name, "kafka.monitor", bootstrap_servers=bootstrap_servers)
        for c in subscriptions:
            monitor.subscribe(c)
        monitor.start()

        return monitor

    monitor = __create_kafka_monitor(kafka_topic, bootstrap_servers, callbacks)
    add_to_namespace(NamespaceKeys.KAFKA_MONITOR, monitor, _globals=globals())


def create_kafka_callback(RE, sophys_utils, logger, kafka_topic, bootstrap_servers, callbacks):
    make_kafka_callback = sophys_utils.make_kafka_callback

    logger.info(f"Connecting to kafka... (IPs: {bootstrap_servers} | Topic: {kafka_topic})")

    try:
        # RE -> Kafka
        RE.subscribe(make_kafka_callback(topic_names=[kafka_topic], bootstrap_servers=bootstrap_servers, backoff_times=[0.1, 1.0]))

        logger.info("Connected to the kafka broker successfully!")

        # Kafka -> sophys-cli
        create_kafka_monitor(kafka_topic, callbacks)
    except (TypeError, NoBrokersAvailable):
        logger.info("Failed to connect to the kafka broker.")

        # Fallback: use everything local, even if `kbl` doesn't work.
        for callback in callbacks:
            RE.subscribe(callback)


def instantiate_devices(logger):
    sophys_devices = importlib.import_module(f"sophys.{EXTENSION}.devices")
    _instantiate_devices = getattr(sophys_devices, "instantiate_devices", None)

    if _instantiate_devices is None:
        D = SimpleNamespace()
        add_to_namespace(NamespaceKeys.DEVICES, D, _globals=globals())

        return

    class StrSimpleNamespace(SimpleNamespace):
        """SimpleNamespace subclass that does not access its elements on __repr__ calls."""

        def __repr__(self):
            return "\n".join(self.__dict__.keys())

    # Leave this last so device instantiation errors do not prevent everything else from working
    D = None
    logger.debug("Instantiating and connecting to devices...")
    _dev = _instantiate_devices()
    D = StrSimpleNamespace(**_dev)
    logger.debug("Instantiation completed successfully!")

    add_to_namespace(NamespaceKeys.DEVICES, D, _globals=globals())

    return _dev


def execute_at_start():
    callbacks = create_callbacks()

    sophys_utils = importlib.import_module(f"sophys.{EXTENSION}.utils")
    default_topic_names = sophys_utils.default_topic_names
    default_bootstrap_servers = sophys_utils.default_bootstrap_servers

    kafka_topic, bootstrap_servers = create_kafka_parameters(default_topic_names, default_bootstrap_servers)

    if not get_from_namespace(NamespaceKeys.LOCAL_MODE, False):
        # Remote mode, only setup the monitor
        # create_kafka_monitor(kafka_topic, bootstrap_servers, callbacks)

        return

    kafka_logger = logging.getLogger("kafka")
    sophys_logger = logging.getLogger("sophys_cli")

    RE = create_run_engine()

    # Kafka callback
    # NOTE: This is needed even in the local setting so that `kbl` works even in this case.
    create_kafka_callback(RE, sophys_utils, kafka_logger, kafka_topic, bootstrap_servers, callbacks)

    _dev = instantiate_devices(sophys_logger)

    from sophys.ema.plans.preprocessors import create_metadata_inserter_preprocessor, create_mnemonic_names_inserter_preprocessor, create_check_device_preprocessor
    RE.preprocessors.append(create_mnemonic_names_inserter_preprocessor(_dev.values()))
    RE.preprocessors.append(create_metadata_inserter_preprocessor())
    RE.preprocessors.append(create_check_device_preprocessor())


execute_at_start()
