import functools
import logging
import importlib

from types import SimpleNamespace

from kafka.errors import NoBrokersAvailable

from bluesky import RunEngine
from bluesky import plans as bp, plan_stubs as bps
from bluesky.callbacks.best_effort import BestEffortCallback
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


sophys_devices = importlib.import_module(f"sophys.{BEAMLINE}.devices")
instantiate_devices = sophys_devices.instantiate_devices

sophys_plans = importlib.import_module(f"sophys.{BEAMLINE}.plans")
globals().update(sophys_plans.__dict__)

sophys_utils = importlib.import_module(f"sophys.{BEAMLINE}.utils")
make_kafka_callback = sophys_utils.make_kafka_callback
default_topic_names = sophys_utils.default_topic_names
default_bootstrap_servers = sophys_utils.default_bootstrap_servers

D = SimpleNamespace(**instantiate_devices())

RE = RunEngineWithoutTracebackOnPause({})
RE.subscribe(BestEffortCallback())

# Logging

root = logging.getLogger()
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] - %(message)s", datefmt="%H:%M:%S")
handler.setFormatter(formatter)
root.addHandler(handler)

root.setLevel("INFO")
handler.setLevel("INFO")

# Kafka callback

kafka_logger = logging.getLogger("kafka")
kafka_logger.setLevel("WARNING")

print(f"Connecting to kafka... (IPs: {default_bootstrap_servers()} | Topics: {default_topic_names()})")
try:
    RE.subscribe(make_kafka_callback(backoff_times=[0.1, 1.0]))
except (TypeError, NoBrokersAvailable):
    print("Failed to connect to the kafka broker.")
else:
    print("Connected to the kafka broker successfully!")

