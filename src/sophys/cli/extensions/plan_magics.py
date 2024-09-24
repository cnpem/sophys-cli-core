from argparse import ArgumentParser, RawDescriptionHelpFormatter
from enum import IntEnum

import functools
import importlib
import inspect

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
    def __init__(self, user_plan_name: str, plan, mode_of_operation: ModeOfOperation):
        self._plan_name = user_plan_name
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

    def create_parser(self):
        def _on_exit_override(*_):
            self._sent_help_message = True

        _a = ArgumentParser(
            self._plan_name,
            description=inspect.getdoc(self._plan),
            formatter_class=RawDescriptionHelpFormatter,
            add_help=True,
            exit_on_error=False
        )
        _a.exit = _on_exit_override

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
        if self._mode_of_operation == ModeOfOperation.Local:
            args = []
            for i in range(0, len(parsed_namespace.args), 2):
                obj_str, pos_str = parsed_namespace.args[i:i+2]
                args.append(self.get_real_devices([obj_str], local_ns)[0])
                args.append(float(pos_str))

            return functools.partial(self._plan, *args)
        if self._mode_of_operation == ModeOfOperation.Remote:
            args = []
            for i in range(0, len(parsed_namespace.args), 2):
                obj_str, pos_str = parsed_namespace.args[i:i+2]
                args.append(obj_str)
                args.append(float(pos_str))

            return BPlan(self._plan.__name__, *args)


class PlanCount(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-d", "--detectors", nargs='+', type=str)
        _a.add_argument("-n", "--num", type=int, default=1)
        _a.add_argument("--delay", type=float, default=0.0)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        num = parsed_namespace.num
        delay = parsed_namespace.delay

        if self._mode_of_operation == ModeOfOperation.Local:
            detector = self.get_real_devices(parsed_namespace.detectors, local_ns)

            return functools.partial(self._plan, detector, num=num, delay=delay)
        if self._mode_of_operation == ModeOfOperation.Remote:
            detector = parsed_namespace.detectors

            return BPlan(self._plan_name, detector, num=num, delay=delay)


class PlanScan(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-d", "--detectors", nargs='+', type=str)
        _a.add_argument("-m", "--motors", nargs='+', type=str)
        _a.add_argument("-n", "--num", type=int, default=1)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        if self._mode_of_operation == ModeOfOperation.Local:
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
        if self._mode_of_operation == ModeOfOperation.Remote:
            detector = parsed_namespace.detectors

            args = []
            motors_str_list = parsed_namespace.motors
            for i in range(0, len(motors_str_list) - 2, 3):
                obj_str, start_str, end_str = motors_str_list[i:i+3]
                args.append(obj_str)
                args.append(float(start_str))
                args.append(float(end_str))

            num = parsed_namespace.num
            if len(motors_str_list) % 3 == 1:
                num = int(motors_str_list[-1])

            return BPlan(self._plan_name, detector, *args, num=num)


class PlanGridScan(PlanCLI):
    def create_parser(self):
        _a = super().create_parser()

        _a.add_argument("-d", "--detectors", nargs='+', type=str)
        _a.add_argument("-m", "--motors", nargs='+', type=str)
        _a.add_argument("-s", "--snake_axes", action="store_true", default=False)

        return _a

    def _create_plan(self, parsed_namespace, local_ns):
        if self._mode_of_operation == ModeOfOperation.Local:
            detector = self.get_real_devices(parsed_namespace.detectors, local_ns)
            args = []
            motors_str_list = parsed_namespace.motors
            for i in range(0, len(motors_str_list), 4):
                obj_str, start_str, end_str, num_str = motors_str_list[i:i+4]
                args.append(self.get_real_devices([obj_str], local_ns)[0])
                args.append(float(start_str))
                args.append(float(end_str))
                args.append(int(num_str))

            return functools.partial(self._plan, detector, *args, snake_axes=parsed_namespace.snake_axes)
        if self._mode_of_operation == ModeOfOperation.Remote:
            raise NotImplementedError


@magics_class
class RealMagics(Magics):
    ...


def register_magic_for_plan(plan_name, plan, plan_whitelist, mode_of_operation: ModeOfOperation):
    """
    Register a plan as a magic with bash-like syntax.

    Parameters
    ----------
    plan_name : str
        The name of the plan, as it will be used by the user.
    plan : generator object
        The plan itself.
    plan_whitelist : dict
        A dictionary of (plan name) -> (plan magic class), defined in each extension.
    mode_of_operation : ModeOfOperation
        Whether to run things locally or via a remote service using httpserver.
    """
    user_plan_name, plan_cls = plan_whitelist[plan_name]
    plan_obj = plan_cls(user_plan_name, plan, mode_of_operation)

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

    record_magic(RealMagics.magics, "line", user_plan_name, __inner)


def get_plans(beamline: str, plan_whitelist: dict):
    """Get all plans for this beamline, that are whitelisted."""
    def __inner(module):
        for maybe_plan_name in dir(module):
            if maybe_plan_name not in plan_whitelist:
                continue
            maybe_plan = getattr(module, maybe_plan_name)
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

