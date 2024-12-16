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

sophys_utils = importlib.import_module(f"sophys.{EXTENSION}.utils")
default_topic_names = sophys_utils.default_topic_names
default_bootstrap_servers = sophys_utils.default_bootstrap_servers

kafka_logger = logging.getLogger("kafka")
sophys_logger = logging.getLogger("sophys_cli")

DB = databroker.Broker.named("temp")
LAST = None


def update_last_data(name, _):
    if name == "stop":
        add_to_namespace(NamespaceKeys.LAST_DATA, DB[-1].table(), _globals=globals())


def create_kafka_monitor(topic_name: str, bootstrap_servers: list[str], subscriptions: list[callable]):
    monitor = ThreadedMonitor(None, [], topic_name, "kafka.monitor", bootstrap_servers=bootstrap_servers)
    for c in subscriptions:
        monitor.subscribe(c)
    monitor.start()

    return monitor


def execute_at_start():
    BEC = BestEffortCallback()
    BEC.disable_plots()

    # NOTE: This is like so because otherwise we either have to force a matplotlib backend
    # , or the table printing functionality doesn't work at all in remote settings.
    # FIXME: This impossibilitates using the graphical callbacks. Find out a better way.
    BEC_callback = functools.partial(BEC, escape=True)

    add_to_namespace(NamespaceKeys.BEST_EFFORT_CALLBACK, BEC, _globals=globals())

    kafka_topic = default_topic_names()[0]
    if get_from_namespace(NamespaceKeys.TEST_MODE, False) and get_from_namespace(NamespaceKeys.LOCAL_MODE, False):
        kafka_topic = kafka_topic.replace(EXTENSION, "test")

    add_to_namespace(NamespaceKeys.KAFKA_TOPIC, kafka_topic, _globals=globals())

    if get_from_namespace(NamespaceKeys.LOCAL_MODE, False):
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

        sophys_devices = importlib.import_module(f"sophys.{EXTENSION}.devices")
        instantiate_devices = sophys_devices.instantiate_devices

        make_kafka_callback = sophys_utils.make_kafka_callback

        # Kafka callback
        # NOTE: This is needed even in the local setting so that `kbl` works even in this case.

        kafka_logger.info(f"Connecting to kafka... (IPs: {default_bootstrap_servers()} | Topic: {kafka_topic})")
        try:
            RE.subscribe(make_kafka_callback(topic_names=[kafka_topic], backoff_times=[0.1, 1.0]))
        except (TypeError, NoBrokersAvailable):
            kafka_logger.info("Failed to connect to the kafka broker.")

            # Fallback: use everything local, even if `dbl` doesn't work.
            RE.subscribe(DB.v1.insert)
            RE.subscribe(BEC_callback)
            RE.subscribe(update_last_data)
        else:
            kafka_logger.info("Connected to the kafka broker successfully!")

            monitor = create_kafka_monitor(kafka_topic, default_bootstrap_servers(), [DB.v1.insert, update_last_data, BEC_callback])
            add_to_namespace(NamespaceKeys.KAFKA_MONITOR, monitor, _globals=globals())

        # Leave this last so device instantiation errors do not prevent everything else from working
        D = None
        sophys_logger.debug("Instantiating and connecting to devices...")
        _dev = instantiate_devices()
        D = SimpleNamespace(**_dev)
        sophys_logger.debug("Instantiation completed successfully!")

        from sophys.ema.plans.preprocessors import create_mnemonic_names_inserter_preprocessor
        RE.preprocessors.append(create_mnemonic_names_inserter_preprocessor(_dev.values()))

        add_to_namespace(NamespaceKeys.RUN_ENGINE, RE, _globals=globals())
        add_to_namespace(NamespaceKeys.DEVICES, D, _globals=globals())

    else:
        monitor = create_kafka_monitor(kafka_topic, default_bootstrap_servers(), [DB.v1.insert, update_last_data, BEC_callback])
        add_to_namespace(NamespaceKeys.KAFKA_MONITOR, monitor, _globals=globals())


execute_at_start()
