from argparse import ArgumentParser
import importlib
import inspect

from IPython.core.magic import Magics, magics_class, record_magic


@magics_class
class RealMagics(Magics):
    ...


def register_magic_for_plan(plan_name, plan):
    plan_inspect = inspect.signature(plan)
    _a = ArgumentParser(prog=plan_name, add_help=False, exit_on_error=False)
    for p in plan_inspect.parameters.values():
        default_val = p.default if p.default is not inspect.Parameter.empty else None
        if p.kind == inspect.Parameter.POSITIONAL_ONLY:
            _a.add_argument(p.name, default=default_val)
        elif p.kind == inspect.Parameter.VAR_POSITIONAL:
            _a.add_argument(p.name, nargs='+')
        else:
            _a.add_argument(f"--{p.name}", default=default_val)

    def __inner(line):
        # TODO: Run the plan
        print(_a.parse_known_args(line.strip().split(' ')))

    record_magic(RealMagics.magics, "line", plan_name, __inner)


def get_plans(beamline: str):
    def __inner(module):
        for maybe_plan_name in dir(module):
            maybe_plan = getattr(module, maybe_plan_name)
            if inspect.isgeneratorfunction(maybe_plan):
                yield (maybe_plan_name, maybe_plan)

    try:
        from bluesky import plans as bp
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
    for plan_name, plan in get_plans("common"):
        register_magic_for_plan(plan_name, plan)
    ipython.register_magics(RealMagics)


def unload_ipython_extension(ipython):
    pass
