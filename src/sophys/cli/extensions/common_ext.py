from .plan_magics import get_plans, register_magic_for_plan, RealMagics, ModeOfOperation
from .tools_magics import KBLMagics

from .plan_magics import PlanMV, PlanCount, PlanScan, PlanGridScan

from ..http_utils import RemoteSessionHandler


PLAN_WHITELIST = {
    "mv": ("mov", PlanMV),
    "count": ("count", PlanCount),
    "scan": ("scan", PlanScan),
    "grid_scan": ("grid_scan", PlanGridScan),
}


def load_ipython_extension(ipython):
    local_mode = ipython.user_ns.get("LOCAL_MODE", False)
    mode_of_op = ModeOfOperation.Local if local_mode else ModeOfOperation.Remote

    for plan_name, plan in get_plans("common", PLAN_WHITELIST):
        register_magic_for_plan(plan_name, plan, PLAN_WHITELIST, mode_of_op)
    ipython.register_magics(RealMagics)

    ipython.register_magics(KBLMagics)

    print("    The custom available commands are:")
    print("    kbl: Open kafka-bluesky-live")
    print("")
    print("")

    if not local_mode:
        remote_session_handler = RemoteSessionHandler("http://10.30.1.50:60610")
        remote_session_handler.start()
        remote_session_handler.ask_for_authentication()

        ipython.push({"_remote_session_handler": remote_session_handler})


def unload_ipython_extension(ipython):
    pass
