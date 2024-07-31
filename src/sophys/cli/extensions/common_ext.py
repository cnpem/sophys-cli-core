from argparse import ArgumentParser

import importlib
import inspect
import math
import typing

from pydantic import validate_call

from IPython.core.magic import Magics, magics_class, record_magic, needs_local_scope


__INS_P = inspect.Parameter


@magics_class
class RealMagics(Magics):
    ...


def get_parameter_type(param: __INS_P) -> tuple[type, str, bool]:
    """
    Get the type and number of a parameter.

    Returns
    -------
    Tuple of:
        type of parameter
        nargs
        whether to transform into a single number if we have a list of one item
    """
    # Get type from the default value
    if (def_type := type(param.default)) not in (type, type(None), __INS_P.empty):
        return def_type, '?', False

    # Get typing.(...) types
    if isinstance(param.annotation, typing._GenericAlias):
        # typing.Sequence[...]
        if hasattr(param.annotation, "_name") and param.annotation._name == "Sequence":
            if any(i in str(param.annotation.__args__) for i in ("float", "int")):
                return float, '+', False
            return str, '+', False

        # Mostly typing.Union[...]
        if any(i in str(param.annotation) for i in ("Sequence", "tuple")):
            return float, '+', True
        if any(i in str(param.annotation) for i in ("float", "int")):
            return float, '?', False
        return str, '?', False

    # Fallback
    nargs = '+' if param.kind in (__INS_P.VAR_POSITIONAL, __INS_P.VAR_KEYWORD) else '?'
    return param.annotation, nargs, False


def filter_maybe(type, iterable):
    res = []
    for i in iterable:
        try:
            res.append(type(i))
        except Exception:
            res.append(i)
    return res


def float_downcast(val):
    if isinstance(val, bool):
        raise Exception
    return float(val)


def int_downcast(val):
    if not isinstance(val, float):
        raise Exception
    if math.ceil(val) != math.floor(val):
        raise Exception
    return int(val)


def bind_and_process_mixed(plan_signature: inspect.Signature, *args, **kwargs):
    ret_args = []
    ret_kwargs = {}

    for name, param in plan_signature.parameters.items():
        if param.kind is __INS_P.POSITIONAL_ONLY:
            if name in kwargs:
                ret_args.append(kwargs[name])
            elif len(args) > 0:
                ret_args.append(args[0])
                args = args[1:]
        elif param.kind is __INS_P.VAR_POSITIONAL:
            if name in kwargs:
                ret_args.extend(i for i in kwargs[name])
            elif len(args) > 0:
                ret_args.extend(i for i in args[0])
                args = args[1:]
        else:
            if name in kwargs:
                ret_kwargs[name] = kwargs[name]
            elif len(args) > 0:
                ret_kwargs[name] = args[0]
                args = args[1:]

    for t in (float_downcast, int_downcast):
        ret_args = filter_maybe(t, ret_args)
        for name, val in ret_kwargs.items():
            ret_kwargs[name] = filter_maybe(t, val) if isinstance(val, typing.Iterable) else filter_maybe(t, [val])[0]

    return ret_args, ret_kwargs


def register_magic_for_plan(plan_name, plan):
    plan_inspect = inspect.signature(plan)

    sent_help_message = False

    def _on_exit_override(*_):
        nonlocal sent_help_message
        sent_help_message = True

    _a = ArgumentParser(prog=plan_name, description=inspect.getdoc(plan), add_help=True, exit_on_error=False)
    _a.exit = _on_exit_override

    argument_data = {}

    for p in plan_inspect.parameters.values():
        default_val = p.default if p.default is not __INS_P.empty else None

        val_type, nargs, cast_on_single_item = get_parameter_type(p)
        argument_data[p.name] = cast_on_single_item

        add_argument_params = {}

        if default_val is not None:
            add_argument_params["default"] = default_val

        if val_type not in (type(None), __INS_P.empty):
            add_argument_params["type"] = val_type

        if nargs is not None:
            add_argument_params["nargs"] = nargs

        _a.add_argument(f"--{p.name}", **add_argument_params)

    @needs_local_scope
    def __inner(line, local_ns):
        parsed_kw_args, parsed_pos_args = _a.parse_known_args(line.strip().split(' '))

        nonlocal sent_help_message
        if sent_help_message:
            sent_help_message = False
            return

        pos_args = []
        kw_args = {}

        try:
            for arg in parsed_pos_args:
                pos_args.append(getattr(local_ns["D"], str(arg), arg))

            for name, arg in parsed_kw_args.__dict__.items():
                if arg is None:
                    continue

                if isinstance(arg, typing.Iterable):
                    if len(arg) == 1 and argument_data[name]:
                        kw_args[name] = getattr(local_ns["D"], str(arg[0]), arg[0])
                    else:
                        kw_args[name] = [getattr(local_ns["D"], str(i), i) for i in arg]
                else:
                    kw_args[name] = arg

            pos_args, kw_args = bind_and_process_mixed(plan_inspect, *pos_args, **kw_args)

            plan_gen = validate_call(plan, config={"arbitrary_types_allowed": True})(*pos_args, **kw_args)
            return local_ns["RE"](plan_gen)
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
