import enum
import functools

from IPython import get_ipython

from .. import BANNER_NAME_EXTEND
from ..http_utils import RemoteSessionHandler


class NamespaceKeys(enum.StrEnum):
    BEST_EFFORT_CALLBACK = "BEC"
    DATABROKER = "DB"
    DEBUG_MODE = "DEBUG"
    DEVICES = "D"
    KAFKA_MONITOR = "KAFKA_MON"
    LAST_DATA = "LAST"
    LOCAL_DATA_SOURCE = "__local_data_source"
    PLANS = "P"
    REMOTE_SESSION_HANDLER = "_remote_session_handler"
    REMOTE_DATA_SOURCE = "__data_source"
    RUN_ENGINE = "RE"


def add_to_namespace(key: NamespaceKeys, value, ipython=None, _globals=None):
    if _globals is not None:
        _globals.update({key: value})
        return

    if ipython is None:
        ipython = get_ipython()

    ipython.push({key: value})


def get_from_namespace(key: NamespaceKeys, default=None, ipython=None, ns=None):
    if ipython is None and ns is None:
        ipython = get_ipython()
    if ns is None:
        ns = ipython.user_ns

    return ns.get(key, default)


def in_debug_mode(local_ns):
    return get_from_namespace(NamespaceKeys.DEBUG_MODE, ns=local_ns)


@functools.lru_cache(maxsize=1)
def render_custom_magics(ipython):
    """Render custom magic descriptions."""
    render = []
    render.append("")
    render.append("The custom available commands are:")
    for registered_magics in ipython.magics_manager.registry.values():
        if hasattr(registered_magics, "description"):
            for desc_item in registered_magics.description():
                name = desc_item[0]
                desc = desc_item[1]

                if len(desc_item) == 2:
                    render.append(f"{name:<{BANNER_NAME_EXTEND}}: {desc}")
                elif len(desc_item) == 3:
                    color = desc_item[2]
                    render.append(f"{color}{name:<{BANNER_NAME_EXTEND}}: {desc}\033[0m")
    render.append("")
    render.append("")
    return render


def setup_remote_session_handler(ipython, address: str):
    _remote_session_handler = RemoteSessionHandler(address)
    _remote_session_handler.start()
    _remote_session_handler.ask_for_authentication()

    add_to_namespace(NamespaceKeys.REMOTE_SESSION_HANDLER, _remote_session_handler, ipython)

    ipython.run_line_magic("reload_devices", "")
    ipython.run_line_magic("reload_plans", "")


def setup_plan_magics(ipython, sophys_name: str, plan_whitelist: dict, mode_of_operation, post_submission_callbacks: list[callable] | None = None):
    from .plan_magics import register_magic_for_plan, get_plans, RealMagics

    if post_submission_callbacks is None:
        post_submission_callbacks = []

    for plan_information, plan in get_plans(sophys_name, plan_whitelist):
        register_magic_for_plan(plan, plan_information, mode_of_operation, post_submission_callbacks)
    ipython.register_magics(RealMagics)
