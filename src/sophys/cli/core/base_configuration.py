import functools
import importlib

from sophys.cli.core import ENVVARS
from sophys.cli.core.magics import NamespaceKeys, add_to_namespace, get_from_namespace


def create_bec(_globals):
    from bluesky.callbacks.best_effort import BestEffortCallback

    BEC = BestEffortCallback()
    BEC.disable_plots()

    # NOTE: This is like so because otherwise we either have to force a matplotlib backend
    # , or the table printing functionality doesn't work at all in remote settings.
    # FIXME: This impossibilitates using the graphical callbacks. Find out a better way.
    BEC_callback = functools.partial(BEC, escape=True)

    add_to_namespace(NamespaceKeys.BEST_EFFORT_CALLBACK, BEC, _globals=_globals)

    return BEC, BEC_callback


def create_callbacks(_globals):
    import databroker

    DB = databroker.Broker.named("temp")
    add_to_namespace(NamespaceKeys.DATABROKER, DB, _globals=_globals)

    def update_last_data(name, _):
        if name == "stop":
            add_to_namespace(NamespaceKeys.LAST_DATA, DB[-1].table(), _globals=_globals)

    BEC, BEC_callback = create_bec(_globals)

    return [DB.v1.insert, update_last_data, BEC_callback]


def create_run_engine(_globals):
    from bluesky import RunEngine
    from bluesky.utils import RunEngineInterrupted

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
    add_to_namespace(NamespaceKeys.RUN_ENGINE, RE, _globals=_globals)

    return RE


def create_kafka_parameters(extension_name, _globals):
    kafka_topic = ENVVARS.KAFKA_TOPIC
    bootstrap_servers = [f"{ENVVARS.KAFKA_HOST}:{ENVVARS.KAFKA_PORT}"]

    in_test_mode = get_from_namespace(NamespaceKeys.TEST_MODE, False, ns=_globals)
    in_local_mode = get_from_namespace(NamespaceKeys.LOCAL_MODE, False, ns=_globals)
    if in_test_mode and in_local_mode:
        kafka_topic = kafka_topic.replace(extension_name, "test")

    add_to_namespace(NamespaceKeys.KAFKA_BOOTSTRAP, bootstrap_servers, _globals=_globals)
    add_to_namespace(NamespaceKeys.KAFKA_TOPIC, kafka_topic, _globals=_globals)

    return kafka_topic, bootstrap_servers


def create_kafka_monitor(kafka_topic, bootstrap_servers, callbacks, _globals):
    from sophys.common.utils.kafka.monitor import ThreadedMonitor

    def __create_kafka_monitor(topic_name: str, bootstrap_servers: list[str], subscriptions: list[callable]):
        monitor = ThreadedMonitor(None, [], topic_name, "kafka.monitor", bootstrap_servers=bootstrap_servers)
        for c in subscriptions:
            monitor.subscribe(c)
        monitor.start()

        return monitor

    monitor = __create_kafka_monitor(kafka_topic, bootstrap_servers, callbacks)
    add_to_namespace(NamespaceKeys.KAFKA_MONITOR, monitor, _globals=_globals)


def create_kafka_callback(RE, logger, kafka_topic, bootstrap_servers, callbacks, _globals):
    from kafka.errors import NoBrokersAvailable
    from sophys.common.utils.kafka import make_kafka_callback

    logger.info(f"Connecting to kafka... (IPs: {bootstrap_servers} | Topic: {kafka_topic})")

    try:
        # RE -> Kafka
        RE.subscribe(make_kafka_callback(topic_names=[kafka_topic], bootstrap_servers=bootstrap_servers, backoff_times=[0.1, 1.0]))

        logger.info("Connected to the kafka broker successfully!")
    except (TypeError, NoBrokersAvailable):
        logger.info("Failed to connect to the kafka broker.")

        # Fallback: use everything local, even if `kbl` doesn't work.
        for callback in callbacks:
            RE.subscribe(callback)
    else:
        # Kafka -> sophys-cli
        create_kafka_monitor(kafka_topic, bootstrap_servers, callbacks, _globals)


def instantiate_devices(logger, extension_name, _globals):
    from types import SimpleNamespace

    sophys_devices = importlib.import_module(f"sophys.{extension_name}.devices")
    _instantiate_devices = getattr(sophys_devices, "instantiate_devices", None)

    if _instantiate_devices is None:
        D = SimpleNamespace()
        add_to_namespace(NamespaceKeys.DEVICES, D, _globals=_globals)

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

    add_to_namespace(NamespaceKeys.DEVICES, D, _globals=_globals)

    return _dev


def execute_at_start(extension_name, _globals):
    import logging

    kafka_logger = logging.getLogger("kafka")
    sophys_logger = logging.getLogger("sophys_cli")

    if extension_name == "skip":
        add_to_namespace(NamespaceKeys.TEST_DATA, "i was here", _globals=_globals)

        return

    callbacks = create_callbacks(_globals)

    kafka_topic, bootstrap_servers = create_kafka_parameters(extension_name, _globals)

    if not get_from_namespace(NamespaceKeys.LOCAL_MODE, False, ns=_globals):
        # Remote mode, only setup the monitor
        create_kafka_monitor(kafka_topic, bootstrap_servers, callbacks, _globals)

        return

    RE = create_run_engine(_globals)

    # Kafka callback
    # NOTE: This is needed even in the local setting so that `kbl` works even in this case.
    create_kafka_callback(RE, kafka_logger, kafka_topic, bootstrap_servers, callbacks, _globals)

    instantiate_devices(sophys_logger, extension_name, _globals)


def load_ipython_extension(ipython):
    extension_name = get_from_namespace(NamespaceKeys.EXTENSION_NAME, ipython=ipython)

    _globals = ipython.user_ns  # Modified by reference
    execute_at_start(extension_name, _globals)
