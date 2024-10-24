import functools

from .. import BANNER_NAME_EXTEND
from ..http_utils import RemoteSessionHandler


def in_debug_mode(local_ns):
    return local_ns["DEBUG"]


@functools.lru_cache(maxsize=1)
def render_custom_magics(ipython):
    render = []
    render.append("")
    render.append("The custom available commands are:")
    for registered_magics in ipython.magics_manager.registry.values():
        if hasattr(registered_magics, "description"):
            render.append("\n".join(f"{name:<{BANNER_NAME_EXTEND}}: {desc}" for name, desc in registered_magics.description()))
    render.append("")
    render.append("")
    return render


def setup_remote_session_handler(ipython, address: str):
    _remote_session_handler = RemoteSessionHandler(address)
    _remote_session_handler.start()
    _remote_session_handler.ask_for_authentication()

    ipython.push({"_remote_session_handler": _remote_session_handler})

    ipython.run_line_magic("reload_devices", "")
    ipython.run_line_magic("reload_plans", "")


def setup_plan_magics(ipython, sophys_name: str, plan_whitelist: dict, mode_of_operation, post_submission_callbacks: list[callable] | None = None):
    from .plan_magics import register_magic_for_plan, get_plans, RealMagics

    if post_submission_callbacks is None:
        post_submission_callbacks = []

    for plan_information, plan in get_plans(sophys_name, plan_whitelist):
        register_magic_for_plan(plan, plan_information, mode_of_operation, post_submission_callbacks)
    ipython.register_magics(RealMagics)
