from argparse import ArgumentParser

import functools
import importlib
import inspect

from IPython.core.magic import Magics, magics_class, record_magic, needs_local_scope

from sophys.common.utils.registry import find_all as registry_find_all


class PlanCLI:
    def __init__(self, plan_name: str, plan):
        self._plan_name = plan_name
        self._plan = plan

        assert self._plan_name == self._plan.__name__

        self._sent_help_message = False

    def get_real_devices(self, device_names: list[str], local_ns):
        """
        Get the objects corresponding to a list of device names.

        Returns
        -------
        A list of device objects, corresponding to the 'device_names' list.
        """

        real_devices = []

        for dev_name in device_names:
            if hasattr(local_ns["D"], dev_name):
                real_devices.append(getattr(local_ns["D"], dev_name))
                continue

            try:
                dev = registry_find_all(name=dev_name)[0]
            except Exception:
                pass
            else:
                real_devices.append(dev)

            raise Exception(f"Could not find detector with name '{dev_name}'.")

        return real_devices

    def create_parser(self):
        def _on_exit_override(*_):
            self._sent_help_message = True

        _a = ArgumentParser(self._plan_name, description=inspect.getdoc(self._plan), add_help=True, exit_on_error=False)
        _a.exit = _on_exit_override

        return _a

    def create_run_callback(self):
        def __inner(parsed_namespace, local_ns):
            if self._sent_help_message:
                self._sent_help_message = False
                return
            return self._create_plan_gen(parsed_namespace, local_ns)

        return __inner

    def _create_plan_gen(self, parsed_namespace, local_ns):
        pass


class PlanCount(PlanCLI):
    def __init__(self, plan):
        super().__init__("count", plan)

    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-d", "--detectors", nargs='+', type=str)
        _a.add_argument("-n", "--num", type=int, default=1)

        return _a

    def _create_plan_gen(self, parsed_namespace, local_ns):
        detector = self.get_real_devices(parsed_namespace.detectors, local_ns)
        num = parsed_namespace.num

        return functools.partial(self._plan, detector, num=num)


class PlanScan(PlanCLI):
    def __init__(self, plan):
        super().__init__("scan", plan)

    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-d", "--detectors", nargs='+', type=str)
        _a.add_argument("-m", "--motors", nargs='+', type=str)
        _a.add_argument("-n", "--num", type=int, default=1)

        return _a

    def _create_plan_gen(self, parsed_namespace, local_ns):
        detector = self.get_real_devices(parsed_namespace.detectors, local_ns)
        args = []
        motors_str_list = parsed_namespace.motors
        for i in range(0, len(motors_str_list) - 2, 3):
            obj_str, start_str, end_str = motors_str_list[i:i+3]
            args.append(self.get_real_devices([obj_str], local_ns)[0])
            args.append(float(start_str))
            args.append(float(end_str))

        num = parsed_namespace.num
        if len(motors_str_list) % 3 == 1:
            num = int(motors_str_list[-1])

        return functools.partial(self._plan, detector, *args, num=num)


PLAN_WHITELIST = {
    "count": PlanCount,
    "scan": PlanScan,
}


@magics_class
class RealMagics(Magics):
    ...


def register_magic_for_plan(plan_name, plan):
    plan_cls = PLAN_WHITELIST[plan_name]
    plan_obj = plan_cls(plan)

    _a = plan_obj.create_parser()
    run_callback = plan_obj.create_run_callback()

    @needs_local_scope
    def __inner(line, local_ns):
        parsed_namespace, _ = _a.parse_known_args(line.strip().split(' '))

        try:
            plan_gen = run_callback(parsed_namespace, local_ns)
            if plan_gen is None:
                return
            return local_ns["RE"](plan_gen())
        except TypeError as e:
            print()
            print("Failed to run the provided plan.")
            print("Reason:")
            print()

            import traceback
            tb = [i.split("\n") for i in traceback.format_exception(TypeError, e, e.__traceback__, limit=1)]
            print("\n".join(f"*** {i}" for item in tb for i in item))

    record_magic(RealMagics.magics, "line", plan_name, __inner)


def get_plans(beamline: str):
    def __inner(module):
        for maybe_plan_name in dir(module):
            if maybe_plan_name not in PLAN_WHITELIST:
                continue
            maybe_plan = getattr(module, maybe_plan_name)
            if inspect.isgeneratorfunction(maybe_plan):
                yield (maybe_plan_name, maybe_plan)

    try:
        from sophys.common.plans import annotated_default_plans as bp
        yield from __inner(bp)
    except AttributeError:
        pass
    try:
        from bluesky import plan_stubs as bps
        yield from __inner(bps)
    except AttributeError:
        pass
    try:
        _p = importlib.import_module(f"sophys.{beamline}.plans")
        yield from __inner(_p)
    except AttributeError:
        pass


def load_ipython_extension(ipython):
    # Automatic generation of plan CLIs
    # What works:
    #   `detectors` sequence (as str)
    #   `args` with (motor, start, stop, num) schema
    #   simple float / int / bool parameters
    # What doesn't:
    #   `args` with different schemas (e.g. list_scan)
    for plan_name, plan in get_plans("common"):
        register_magic_for_plan(plan_name, plan)
    ipython.register_magics(RealMagics)


def unload_ipython_extension(ipython):
    pass
