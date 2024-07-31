from .plan_magics import get_plans, register_magic_for_plan, RealMagics

from .plan_magics import PlanCount, PlanScan


PLAN_WHITELIST = {
    "count": PlanCount,
    "scan": PlanScan,
}


def load_ipython_extension(ipython):
    for plan_name, plan in get_plans("common", PLAN_WHITELIST):
        register_magic_for_plan(plan_name, plan, PLAN_WHITELIST)
    ipython.register_magics(RealMagics)


def unload_ipython_extension(ipython):
    pass
