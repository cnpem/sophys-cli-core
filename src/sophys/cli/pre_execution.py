import importlib
import sys

from kafka.errors import NoBrokersAvailable

from bluesky import RunEngine
from bluesky import plans as bp, plan_stubs as bps
from bluesky.callbacks.best_effort import BestEffortCallback

__beamline_module = importlib.import_module(f"sophys.{BEAMLINE}")
sys.modules["__beamline_module"] = __beamline_module

from __beamline_module.devices import instantiate_devices
from __beamline_module.plans import *
from __beamline_module.utils import make_kafka_callback

D = instantiate_devices()

RE = RunEngine({})
RE.subscribe(BestEffortCallback())

print("Connecting to kafka...")
try:
    RE.subscribe(make_kafka_callback(backoff_times=[0.1, 1.0]))
except (TypeError, NoBrokersAvailable):
    print("Failed to connect to the kafka broker.")
else:
    print("Connected to the kafka broker successfully!")


