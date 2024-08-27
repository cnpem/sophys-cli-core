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

sophys_utils = importlib.import_module(f"sophys.{BEAMLINE}.utils")
default_topic_names = sophys_utils.default_topic_names
default_bootstrap_servers = sophys_utils.default_bootstrap_servers

kafka_logger = logging.getLogger("kafka")
sophys_logger = logging.getLogger("sophys_cli")

DB = databroker.Broker.named("temp")
LAST = None


def update_last_data(name, _):
    if name == "stop":
        globals().update({"LAST": DB[-1].table()})


def create_kafka_monitor(topic_name: str, subscriptions: list[callable]):
    monitor = ThreadedMonitor(None, [], topic_name, "kafka.monitor")
    for c in subscriptions:
        monitor.subscribe(c)
    monitor.start()

    return monitor


def execute_at_start():
    if LOCAL_MODE:
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

        sophys_devices = importlib.import_module(f"sophys.{BEAMLINE}.devices")
        instantiate_devices = sophys_devices.instantiate_devices

        sophys_plans = importlib.import_module(f"sophys.{BEAMLINE}.plans")
        globals().update(sophys_plans.__dict__)

        make_kafka_callback = sophys_utils.make_kafka_callback

        # Kafka callback
        # NOTE: This is needed even in the local setting so that `kbl` works even in this case.

        kafka_logger.info(f"Connecting to kafka... (IPs: {default_bootstrap_servers()} | Topics: {default_topic_names()})")
        try:
            RE.subscribe(make_kafka_callback(backoff_times=[0.1, 1.0]))
        except (TypeError, NoBrokersAvailable):
            kafka_logger.info("Failed to connect to the kafka broker.")

            # Fallback: use everything local, even if `dbl` doesn't work.
            RE.subscribe(DB.v1.insert)
            RE.subscribe(BestEffortCallback())
            RE.subscribe(update_last_data)
        else:
            kafka_logger.info("Connected to the kafka broker successfully!")

            monitor = create_kafka_monitor(default_topic_names()[0], [DB.v1.insert, update_last_data, BestEffortCallback()])
            globals().update({"KAFKA_MON": monitor})

        # Leave this last so device instantiation errors do not prevent everything else from working
        D = None
        sophys_logger.debug("Instantiating and connecting to devices...")
        D = SimpleNamespace(**instantiate_devices())
        sophys_logger.debug("Instantiation completed successfully!")

        globals().update({"RE": RE, "D": D})

    else:
        monitor = create_kafka_monitor(default_topic_names()[0], [DB.v1.insert, update_last_data, BestEffortCallback()])
        globals().update({"KAFKA_MON": monitor})


execute_at_start()
