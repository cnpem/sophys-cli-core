from .plan_magics import get_plans, register_magic_for_plan, RealMagics, ModeOfOperation

from .plan_magics import PlanCount, PlanScan, PlanGridScan


PLAN_WHITELIST = {
    "count": PlanCount,
    "scan": PlanScan,
    "grid_scan": PlanGridScan,
}


def load_ipython_extension(ipython):
    for plan_name, plan in get_plans("common", PLAN_WHITELIST):
        register_magic_for_plan(plan_name, plan, PLAN_WHITELIST, ModeOfOperation.Local)
    ipython.register_magics(RealMagics)


def unload_ipython_extension(ipython):
    pass
