from argparse import ArgumentParser, RawDescriptionHelpFormatter
from enum import IntEnum
from typing import Annotated

import functools
import importlib
import inspect

from pydantic import BaseModel, ValidationError

from IPython.core.magic import Magics, magics_class, record_magic, needs_local_scope

from sophys.common.utils.registry import find_all as registry_find_all

from . import in_debug_mode

try:
    from bluesky_queueserver_api.item import BPlan
    remote_control_available = True
except ImportError:
    remote_control_available = False


class ModeOfOperation(IntEnum):
    Local = 0
    Remote = 1


class NoRemoteControlException(Exception):
    ...


class PlanCLI:
    def __init__(self, user_plan_name: str, plan_name: str, plan, mode_of_operation: ModeOfOperation):
        self._user_plan_name = user_plan_name
        self._plan_name = plan_name
        self._plan = plan

        self._mode_of_operation = mode_of_operation

        self._sent_help_message = False

    def get_real_devices(self, device_names: list[str], local_ns):
        """
        Get the objects corresponding to a list of device names.

        Returns
        -------
        A list of device objects, corresponding to the 'device_names' list.

        Throws
        ------
        Exception - When a device with the specified name could not be found.
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
                continue

            raise Exception(f"Could not find detector with name '{dev_name}'.")

        return real_devices

    def get_real_devices_if_needed(self, device_names: list[str], local_ns):
        """
        Get the objects corresponding to a list of device names, if needed.
        Otherwise, simply return the names as they are.

        Returns
        -------
        A list of device objects, corresponding to the 'device_names' list.

        Throws
        ------
        Exception - When a device with the specified name could not be found.
        """
        if self._mode_of_operation == ModeOfOperation.Local:
            return self.get_real_devices(device_names, local_ns)
        return device_names

    def parse_varargs(self, args, local_ns, with_final_num=False, default_num=None):
        """Parse '*args' plan arguments."""

        class MvModel(BaseModel):
            device_name: Annotated[str, "device"]
            position: float

            def __init__(self, device_name: str, position: float, **kwargs):
                super().__init__(device_name=device_name, position=position, **kwargs)

        class ScanModel(BaseModel):
            motor_name: Annotated[str, "device"]
            start: float
            stop: float

            def __init__(self, motor_name: str, start: float, stop: float, **kwargs):
                super().__init__(motor_name=motor_name, start=start, stop=stop, **kwargs)

        class GridScanModel(BaseModel):
            motor_name: Annotated[str, "device"]
            start: float
            stop: float
            number: int

            def __init__(self, motor_name: str, start: float, stop: float, number: int, **kwargs):
                super().__init__(motor_name=motor_name, start=start, stop=stop, number=number, **kwargs)

        __VARARGS_VALIDATION = [
            (4, GridScanModel), (3, ScanModel), (2, MvModel)
        ]

        true_n_args, true_cls = None, None
        for n_args, cls in __VARARGS_VALIDATION:
            if len(args) < n_args:
                continue

            try:
                cls(*args[:n_args])
            except ValidationError:
                continue

            true_n_args = n_args
            true_cls = cls
            break

        if true_cls is None:
            raise Exception("No suitable validation class was found.")

        parsed = []
        for i in range(0, len(args) - (true_n_args - 1), true_n_args):
            model = true_cls(*args[i:i+true_n_args])

            for field_name, field_info in model.model_fields.items():
                field_data = getattr(model, field_name)
                if "device" in field_info.metadata:
                    field_data = self.get_real_devices_if_needed([field_data], local_ns)[0]
                parsed.append(field_data)

        if with_final_num and len(args) % true_n_args == 1:
            return parsed, int(args[-1])
        return parsed, default_num

    def parse_md(self, parsed_namespace):
        if parsed_namespace.md is None or len(parsed_namespace.md) == 0:
            return {}

        md = [j for i in parsed_namespace.md for j in i]
        md_it = (i.partition('=') for i in md)
        md = {k: v.strip('\" ') for k, _, v in md_it}
        return md

    def create_parser(self):
        def _on_exit_override(*_):
            self._sent_help_message = True

        _a = ArgumentParser(
            self._user_plan_name,
            description=inspect.getdoc(self._plan),
            formatter_class=RawDescriptionHelpFormatter,
            add_help=True,
            exit_on_error=False
        )
        _a.exit = _on_exit_override

        _a.add_argument("-d", "--detectors", nargs='*', type=str, required=False, default=[])
        _a.add_argument("--md", nargs="*", action="append")

        return _a

    def create_run_callback(self):
        def __inner(parsed_namespace, local_ns):
            if self._sent_help_message:
                self._sent_help_message = False
                return

            if self._mode_of_operation == ModeOfOperation.Remote and not remote_control_available:
                raise NoRemoteControlException

            return self._create_plan(parsed_namespace, local_ns)

        return __inner

    def _create_plan(self, parsed_namespace, local_ns):
        """
        Create the plan to run.

        In local mode, it returns a generator of the plan. In remote mode,
        it returns a `BPlan` instance with the proper arguments.
        """
        pass


class PlanMV(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("args", nargs='+', type=str)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        args, _ = self.parse_varargs(parsed_namespace.args, local_ns)

        if self._mode_of_operation == ModeOfOperation.Local:
            return functools.partial(self._plan, *args)
        if self._mode_of_operation == ModeOfOperation.Remote:
            return BPlan(self._plan.__name__, *args)


class PlanCount(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-n", "--num", type=int, default=1)
        _a.add_argument("--delay", type=float, default=0.0)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        detector = self.get_real_devices_if_needed(parsed_namespace.detectors, local_ns)
        num = parsed_namespace.num
        delay = parsed_namespace.delay
        md = self.parse_md(parsed_namespace)

        if self._mode_of_operation == ModeOfOperation.Local:
            return functools.partial(self._plan, detector, num=num, delay=delay, md=md)
        if self._mode_of_operation == ModeOfOperation.Remote:
            return BPlan(self._plan_name, detector, num=num, delay=delay, md=md)


class PlanScan(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-m", "--motors", nargs='+', type=str)
        _a.add_argument("-n", "--num", type=int, default=1)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        detector = self.get_real_devices_if_needed(parsed_namespace.detectors, local_ns)
        _args = parsed_namespace.motors
        _num = parsed_namespace.num
        args, num = self.parse_varargs(_args, local_ns, with_final_num=True, default_num=_num)
        md = self.parse_md(parsed_namespace)

        if self._mode_of_operation == ModeOfOperation.Local:
            return functools.partial(self._plan, detector, *args, num=num, md=md)
        if self._mode_of_operation == ModeOfOperation.Remote:
            return BPlan(self._plan_name, detector, *args, num=num, md=md)


class PlanGridScan(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-m", "--motors", nargs='+', type=str)
        _a.add_argument("-s", "--snake_axes", action="store_true", default=False)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        detector = self.get_real_devices_if_needed(parsed_namespace.detectors, local_ns)
        _args = parsed_namespace.motors
        args, _ = self.parse_varargs(_args, local_ns)
        md = self.parse_md(parsed_namespace)

        snake = parsed_namespace.snake_axes

        if self._mode_of_operation == ModeOfOperation.Local:
            return functools.partial(self._plan, detector, *args, snake_axes=snake, md=md)
        if self._mode_of_operation == ModeOfOperation.Remote:
            return BPlan(self._plan_name, detector, *args, snake_axes=snake, md=md)


class PlanAdaptiveScan(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-t", "--target_field", type=str)
        _a.add_argument("-m", "--motor", type=str)
        _a.add_argument("-st", "--start", type=float)
        _a.add_argument("-sp", "--stop", type=float)
        _a.add_argument("-mins", "--min_step", type=float)
        _a.add_argument("-maxs", "--max_step", type=float)
        _a.add_argument("-td", "--target_delta", type=float)
        _a.add_argument("-b", "--backstep", type=bool)
        _a.add_argument("-th", "--threshold", type=float, default=0.8)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        detector = self.get_real_devices_if_needed(parsed_namespace.detectors, local_ns)
        md = self.parse_md(parsed_namespace)

        target_field = parsed_namespace.target_field
        motor = self.get_real_devices_if_needed(parsed_namespace.motor, local_ns)
        start = parsed_namespace.start
        stop = parsed_namespace.stop
        min_step = parsed_namespace.min_step
        max_step = parsed_namespace.max_step
        target_delta = parsed_namespace.target_delta
        backstep = parsed_namespace.backstep
        threshold = parsed_namespace.threshold

        if self._mode_of_operation == ModeOfOperation.Local:
            return functools.partial(self._plan, detector, target_field=target_field, motor=motor, start=start, stop=stop, min_step=min_step, max_step=max_step, target_delta=target_delta, backstep=backstep, threshold=threshold, md=md)
        if self._mode_of_operation == ModeOfOperation.Remote:
            return BPlan(self._plan_name, detector, target_field=target_field, motor=motor, start=start, stop=stop, min_step=min_step, max_step=max_step, target_delta=target_delta, backstep=backstep, threshold=threshold, md=md)


@magics_class
class RealMagics(Magics):
    ...


class PlanInformation(BaseModel):
    plan_name: str
    user_name: str
    plan_class: object
    extra_props: dict = {}

    def __init__(self, plan_name: str, user_name: str, plan_class: PlanCLI, **kwargs):
        super().__init__(plan_name=plan_name, user_name=user_name, plan_class=plan_class, extra_props=kwargs)


def register_magic_for_plan(plan, plan_info: PlanInformation, mode_of_operation: ModeOfOperation):
    """
    Register a plan as a magic with bash-like syntax.

    Parameters
    ----------
    plan : generator object
        The plan itself.
    plan_info : PlanInformation
        The PlanInformation object for the given plan.
    mode_of_operation : ModeOfOperation
        Whether to run things locally or via a remote service using httpserver.
    """
    plan_obj = plan_info.plan_class(plan_info.user_name, plan_info.plan_name, plan, mode_of_operation)

    _a = plan_obj.create_parser()
    run_callback = plan_obj.create_run_callback()

    @needs_local_scope
    def __inner(line, local_ns):
        parsed_namespace, _ = _a.parse_known_args(line.strip().split(' '))

        try:
            plan = run_callback(parsed_namespace, local_ns)
            if plan is None:
                return

            if mode_of_operation == ModeOfOperation.Local:
                ret = local_ns["RE"](plan())
                finish_msg = "Plan has finished successfully!"

                if ret is None:
                    finish_msg = "Plan has paused!"
                elif len(ret) > 0:
                    finish_msg += f" | Run UID: {ret[0]}"

                return finish_msg
            if mode_of_operation == ModeOfOperation.Remote:
                handler = local_ns.get("_remote_session_handler", None)
                if handler is None:
                    raise NoRemoteControlException

                manager = handler.get_authorized_manager()
                response = manager.item_execute(plan)

                if response["success"]:
                    finish_msg = "Plan has been submitted successfully!"
                else:
                    finish_msg = f"Failed to submit plan to the remote server! Reason: {response["msg"]}"

                return finish_msg
        except Exception as e:
            print()
            print("Failed to run the provided plan.")
            print("Reason:")
            print()

            debug_mode = in_debug_mode(local_ns)
            limit = None if debug_mode else 1

            import traceback
            tb = [i.split("\n") for i in traceback.format_exception(TypeError, e, e.__traceback__, limit=limit, chain=False)]
            print("\n".join(f"*** {i}" for item in tb for i in item))

    record_magic(RealMagics.magics, "line", plan_info.user_name, __inner)


class PlanWhitelist(list[PlanInformation]):
    def find_by_plan_name(self, plan_name: str):
        return next(filter(lambda pi: pi.plan_name == plan_name, self))

    def __contains__(self, o):
        if isinstance(o, str):
            return any(plan_information.plan_name == o for plan_information in self)
        return super().__contains__(o)

    def __and__(self, o):
        if isinstance(o, set):
            return {pi.user_name for pi in self if pi.plan_name in o}
        return super().__and__(o)


def get_plans(beamline: str, plan_whitelist: PlanWhitelist):
    """Get all plans for this beamline, that are whitelisted."""
    def __inner(module):
        for maybe_plan_name in dir(module):
            if maybe_plan_name not in plan_whitelist:
                continue

            plan_information = plan_whitelist.find_by_plan_name(maybe_plan_name)
            plan = getattr(module, maybe_plan_name)
            yield (plan_information, plan)

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

