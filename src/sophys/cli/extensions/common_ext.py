from .plan_magics import get_plans, register_magic_for_plan, RealMagics, ModeOfOperation
from .tools_magics import KBLMagics, HTTPMagics

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

    if not local_mode:
        print("    reload_devices: Reload the available devices list (D).")
        print("    reload_plans: Reload the available plans list (P).")

        _remote_session_handler = RemoteSessionHandler("http://spu-ioc:60610")
        _remote_session_handler.start()
        _remote_session_handler.ask_for_authentication()

        ipython.push({"_remote_session_handler": _remote_session_handler})

        ipython.register_magics(HTTPMagics)
        ipython.magics_manager.registry["HTTPMagics"].plan_whitelist = PLAN_WHITELIST

        ipython.run_line_magic("reload_devices", "")
        ipython.run_line_magic("reload_plans", "")
    else:
        ipython.push({"P": set(i[0] for i in get_plans("common", PLAN_WHITELIST))})

    print("")
    print("")


def unload_ipython_extension(ipython):
    pass
