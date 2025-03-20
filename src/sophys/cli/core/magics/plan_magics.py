from argparse import ArgumentParser, RawDescriptionHelpFormatter
from enum import IntEnum
from typing import Annotated

import importlib
import inspect

from pydantic import BaseModel, ValidationError

from IPython.core.magic import Magics, magics_class, record_magic, needs_local_scope

from sophys.common.utils.registry import find_all as registry_find_all

from . import in_debug_mode, NamespaceKeys, get_from_namespace, add_to_namespace

try:
    remote_control_available = True
except ImportError:
    remote_control_available = False


class ModeOfOperation(IntEnum):
    Local = 0
    Remote = 1
    Test = 2


class ExceptionHandlerReturnValue(IntEnum):
    EXIT_QUIET = 0
    EXIT_VERBOSE = 1
    RETRY = 2


class NoRemoteControlException(Exception):
    ...


class PlanCLI:
    """
    Base class for Bluesky plans.

    Attributes
    ----------
    pre_processing_md : list of callables
        This represents a collection of pre-processing steps to apply to metadata
        before passing it to the plan. The functions have the following signature:
            (*devices in usage by the plan, metadata dict) -> updated metadata dict
    """

    def __init__(self, user_plan_name: str, plan_name: str, plan, mode_of_operation: ModeOfOperation):
        self._user_plan_name = user_plan_name
        self._plan_name = plan_name
        self._plan = plan

        self._mode_of_operation = mode_of_operation

        self._sent_help_message = False

        self.pre_processing_md = []

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

        if self._mode_of_operation == ModeOfOperation.Test:
            return device_names

        for device_name in device_names:
            if device_name not in get_from_namespace(NamespaceKeys.DEVICES, ns=local_ns):
                exc_msg = f"""
There is no device named '{device_name}' available.

It may be a typo (check your spelling), and then try again.

It may also be the case that the connection failed on startup.
Please check the IOC is up and reachable, and run 'reload_environment' to try again.

If none of the mentioned worked, it is probably a bug. In this case, please contact the reponsible personnel for support.
"""
                raise Exception(exc_msg)

        return device_names

    def parse_varargs(self, args, local_ns, with_final_num=False, default_num=None):
        """
        Parse '*args' plan arguments.

        Returns
        -------
        tuple of (parsed arguments, number of points, list of device names).
        """

        class MvModel(BaseModel):
            device_name: Annotated[str, "device"]
            position: float

            def __init__(self, device_name: str, position: float, **kwargs):
                super().__init__(device_name=device_name, position=position, **kwargs)

        class ReadModel(BaseModel):
            device_name: Annotated[str, "device"]

            def __init__(self, device_name: str, **kwargs):
                super().__init__(device_name=device_name, **kwargs)

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
            (4, GridScanModel), (3, ScanModel), (2, MvModel), (1, ReadModel)
        ]

        true_n_args, true_cls = None, None
        for n_args, cls in __VARARGS_VALIDATION:
            if len(args) - (1 if with_final_num else 0) < n_args:
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

        devices = []
        parsed = []
        for i in range(0, len(args) - (true_n_args - 1), true_n_args):
            model = true_cls(*args[i:i+true_n_args])

            for field_name, field_info in model.model_fields.items():
                field_data = getattr(model, field_name)
                if "device" in field_info.metadata:
                    devices.append(field_data)
                    field_data = self.get_real_devices_if_needed([field_data], local_ns)[0]
                parsed.append(field_data)

        if with_final_num and len(args) % true_n_args == 1:
            return parsed, int(args[-1]), devices
        return parsed, default_num, devices

    def parse_md(self, *devices, ns):
        if ns.md is None or len(ns.md) == 0:
            md = {}
        else:
            md = [j for i in ns.md for j in i]
            md_it = (i.partition('=') for i in md)
            md = {k: v.strip('\"\' ') for k, _, v in md_it}

        for preproc in self.pre_processing_md:
            md = preproc(*devices, md=md)

        return md

    def create_parser(self):
        def _on_exit_override(*_):
            self._sent_help_message = True

        _a = ArgumentParser(
            self._user_plan_name,
            description=self._description(),
            usage=self._usage(),
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

    def _description(self):
        """Description of the plan on the CLI help page."""
        return inspect.getdoc(self._plan)

    def _usage(self):
        """Usage description of the plan on the CLI help page."""
        return None


@magics_class
class RealMagics(Magics):
    ...


class PlanInformation(BaseModel):
    """
    Container for instantiation information about a plan magic.

    Attributes
    ----------
    plan_name : str
        The original plan name, as it is defined by the source packages.
    user_name : str
        The name that will be used as the magic in sophys-cli.
        It doesn't need to be equal to plan_name.
    plan_class : PlanCLI subclass
        The class defining the magic interface and behavior.
    extra_props : dict
        Additional properties to configure on the 'plan_class' instantiated
        object. Currently the following keys have meaning:

        pre_processing_md: Callables to do additional processing on the
        'md' field, before submitting it. See the PlanCLI documentation
        for more information on that.

        Other keys can be attributed meaning and used by extensions too,
        in case they want to modify some behavior at this level.
    """

    plan_name: str
    user_name: str
    plan_class: object
    extra_props: dict = {}

    def __init__(self, plan_name: str, user_name: str, plan_class: PlanCLI, **kwargs):
        super().__init__(plan_name=plan_name, user_name=user_name, plan_class=plan_class, extra_props=kwargs)

    def apply_to_plan(self, plan_obj: PlanCLI):
        """Apply 'extra_props' defined properties into the instantiated object."""
        if "pre_processing_md" in self.extra_props:
            plan_obj.pre_processing_md = self.extra_props["pre_processing_md"]


class PlanWhitelist(list[PlanInformation]):
    """
    Container for instantiation information about an extension's plan magics.

    Parameters
    ----------
    *infos : list of PlanInformation
        A list of PlanInformation instances describing all the plan magics to
        instantiate.
    **general_extra_props : dict
        A relation of additional properties to apply to all PlanInformation
        objects. It directly updates the PlanInformation's 'extra_props' fields.
    """

    def __init__(self, *infos, **general_extra_props):
        super().__init__(infos)

        for plan_info in self:
            plan_info.extra_props.update(general_extra_props)

    def find_by_plan_name(self, plan_name: str):
        return filter(lambda pi: pi.plan_name == plan_name, self)

    def __contains__(self, o):
        if isinstance(o, str):
            return any(plan_information.plan_name == o for plan_information in self)
        return super().__contains__(o)

    def __and__(self, o):
        if isinstance(o, set):
            return {pi.user_name for pi in self if pi.plan_name in o}
        return super().__and__(o)


def _local_mode_plan_execute(RE, plan, post_submission_callbacks):
    """Execute a plan in a local RunEngine context."""
    ret = RE(plan)
    finish_msg = "Plan has finished successfully!"

    if ret is None:
        finish_msg = "Plan has paused!"
    elif len(ret) > 0:
        finish_msg += f" | Run UID: {ret[0]}"

    for sub in post_submission_callbacks:
        sub()

    return finish_msg


def _remote_mode_plan_execute(manager, plan, post_submission_callbacks):
    """Execute a plan in a remote queueserver context."""
    response = manager.item_execute(plan)

    if response["success"]:
        finish_msg = "Plan has been submitted successfully!"
    else:
        finish_msg = f"Failed to submit plan to the remote server! Reason: {response["msg"]}"

    post_submission_success = True
    for sub_cb in post_submission_callbacks:
        ret = sub_cb()
        post_submission_success &= (ret or (ret is None))

    if not post_submission_success:
        finish_msg = "Plan has been submitted, but failed at a later point."

    return finish_msg


def register_magic_for_plan(
        plan,
        plan_info: PlanInformation,
        mode_of_operation: ModeOfOperation,
        post_submission_callbacks: list[callable],
        exception_handlers: dict[type(Exception), callable]
        ):
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
    exception_handlers : map of Exception types to callbacks
        This mapping provides a way for extensions to customize how they handle certain
        exception thrown at or right before plan execution.

        The callbacks receive the original exception object, and the local namespace,
        and return an object of ExceptionHandlerReturnValue indicating how to proceed.
    """
    plan_obj = plan_info.plan_class(plan_info.user_name, plan_info.plan_name, plan, mode_of_operation)
    plan_info.apply_to_plan(plan_obj)

    _a = plan_obj.create_parser()
    run_callback = plan_obj.create_run_callback()

    @needs_local_scope
    def __inner(line, local_ns):
        while True:
            try:
                parsed_namespace, _ = _a.parse_known_args(line.strip().split(' '))
            except Exception as e:
                # FIXME: There should be a better way to check this condition.
                if "-h" not in line:
                    print("Parsing the plan arguments has failed:")
                    print("  " + str(e))
                return

            try:
                plan = run_callback(parsed_namespace, local_ns)
                if plan is None:
                    return

                if mode_of_operation == ModeOfOperation.Local:
                    return _local_mode_plan_execute(local_ns["RE"], plan(), post_submission_callbacks)
                if mode_of_operation == ModeOfOperation.Remote:
                    handler = get_from_namespace(NamespaceKeys.REMOTE_SESSION_HANDLER, ns=local_ns)
                    if handler is None:
                        raise NoRemoteControlException

                    manager = handler.get_authorized_manager()
                    return _remote_mode_plan_execute(manager, plan, post_submission_callbacks)
                if mode_of_operation == ModeOfOperation.Test:
                    add_to_namespace(NamespaceKeys.TEST_DATA, plan)
                    return
            except Exception as e:
                if type(e) in exception_handlers:
                    match exception_handlers[type(e)](e, local_ns):
                        case ExceptionHandlerReturnValue.EXIT_QUIET:
                            return
                        case ExceptionHandlerReturnValue.EXIT_VERBOSE:
                            pass
                        case ExceptionHandlerReturnValue.RETRY:
                            continue

                print()
                print("Failed to run the provided plan.")
                print("Reason:")
                print()

                debug_mode = in_debug_mode(local_ns)
                limit = None if debug_mode else 1

                import traceback
                tb = [i.split("\n") for i in traceback.format_exception(TypeError, e, e.__traceback__, limit=limit, chain=False)]
                print("\n".join(f"*** {i}" for item in tb for i in item))

                return

    record_magic(RealMagics.magics, "line", plan_info.user_name, __inner)


def get_plans(beamline: str, plan_whitelist: PlanWhitelist):
    """Get all plans for this beamline, that are whitelisted."""
    visited_plan_names = set()

    def __inner(module):
        for maybe_plan_name in dir(module):
            if maybe_plan_name not in plan_whitelist:
                continue
            if maybe_plan_name in visited_plan_names:
                continue

            plans_information = plan_whitelist.find_by_plan_name(maybe_plan_name)
            for plan_information in plans_information:
                plan = getattr(module, maybe_plan_name)
                visited_plan_names.add(maybe_plan_name)
                yield (plan_information, plan)

    try:
        _p = importlib.import_module(f"sophys.{beamline}.plans")
        yield from __inner(_p)
    except AttributeError:
        pass
    try:
        from sophys.common.plans import annotated_default_plans as bp
        yield from __inner(bp)
    except AttributeError:
        pass
    try:
        from sophys.common.plans import expanded_plan_stubs as bps
        yield from __inner(bps)
    except AttributeError:
        pass
