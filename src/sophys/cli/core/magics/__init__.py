import enum
import functools

from contextlib import contextmanager

from IPython import get_ipython

from .. import BANNER_NAME_EXTEND
from ..http_utils import RemoteSessionHandler


class NamespaceKeys(enum.StrEnum):
    BEST_EFFORT_CALLBACK = "BEC"
    BLACKLISTED_DESCRIPTIONS = "__blacklisted_magic_descriptions"
    COLORIZED_OUTPUT = "_COLORIZED"
    DATABROKER = "DB"
    DEBUG_MODE = "DEBUG"
    DEVICES = "D"
    KAFKA_MONITOR = "KAFKA_MON"
    LAST_DATA = "LAST"
    LOCAL_DATA_SOURCE = "__local_data_source"
    LOCAL_MODE = "LOCAL_MODE"
    PERSISTENT_METADATA = "__persistent_metadata"
    PLANS = "P"
    REMOTE_SESSION_HANDLER = "_remote_session_handler"
    REMOTE_DATA_SOURCE = "__data_source"
    RUN_ENGINE = "RE"
    TEST_MODE = "TEST_MODE"


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


def get_color(color: str) -> str:
    if get_from_namespace(NamespaceKeys.COLORIZED_OUTPUT, default=True):
        return color
    return ""


@functools.lru_cache(maxsize=1)
def render_custom_magics(ipython):
    """Render custom magic descriptions."""
    blacklist = get_from_namespace(NamespaceKeys.BLACKLISTED_DESCRIPTIONS, default=set(), ipython=ipython)

    _rendered_magics = []

    render = []
    render.append("")
    render.append("The custom available commands are:")
    for registered_magics in ipython.magics_manager.registry.values():
        if hasattr(registered_magics, "description"):
            _rendered_magics.append((len(render), registered_magics))
            for desc_item in registered_magics.description():
                name = desc_item[0]
                desc = desc_item[1]

                if name in blacklist:
                    continue

                if name == desc == "":
                    render.append("")
                elif len(desc_item) == 2:
                    render.append(f"{name:<{BANNER_NAME_EXTEND}}: {desc}")
                elif len(desc_item) == 3:
                    color = desc_item[2]
                    render.append(f"{color}{name:<{BANNER_NAME_EXTEND}}: {desc}{get_color('\033[0m')}")

    # Add extra spacing between commands of different colors
    from itertools import pairwise
    _extra_index = 0
    for (_, fst), (pos, snd) in pairwise(_rendered_magics):
        fst_d = fst.description()[-1]
        snd_d = snd.description()[0]

        if fst_d[-1] != snd_d[-1]:
            render.insert(pos + _extra_index, "")
            _extra_index += 1

    render.append("")
    render.append("")
    return render


def setup_remote_session_handler(ipython, address: str):
    _remote_session_handler = RemoteSessionHandler(address)
    _remote_session_handler.start()
    _remote_session_handler.ask_for_authentication()

    add_to_namespace(NamespaceKeys.REMOTE_SESSION_HANDLER, _remote_session_handler, ipython)

    try:
        ipython.run_line_magic("reload_devices", "")
        ipython.run_line_magic("reload_plans", "")
    except Exception:
        print(f"Could not connect to httpserver at address '{address}'.")


def setup_plan_magics(ipython, sophys_name: str, plan_whitelist: dict, mode_of_operation, post_submission_callbacks: list[callable] | None = None):
    from .plan_magics import register_magic_for_plan, get_plans, RealMagics

    if post_submission_callbacks is None:
        post_submission_callbacks = []

    for plan_information, plan in get_plans(sophys_name, plan_whitelist):
        register_magic_for_plan(plan, plan_information, mode_of_operation, post_submission_callbacks)
    ipython.register_magics(RealMagics)


@contextmanager
def handle_ctrl_c_signals(callbacks: dict | None = None, max_signal_count: int | None = 10):
    """
    Context manager for intercepting and handling SIGINTs in a clean way.

    Parameters
    ----------
    callbacks : dict, optional
        Callbacks in the form (Ctrl+C count) -> (Callable) for making stuff when getting SIGINTs.
    max_signal_count : int, optional
        Maximum number of SIGINTs to handle before returning to the original handler. Defaults to 10.
    """

    if callbacks is None:
        callbacks = dict()

    import signal

    _original_handler = signal.getsignal(signal.SIGINT)
    _released = False
    _count = 0

    def _release():
        nonlocal _released
        if _released:
            return

        signal.signal(signal.SIGINT, _original_handler)
        _released = True

    def _handler(signum, frame):
        nonlocal _count
        _count += 1

        if _count > max_signal_count and not _released:
            _release()
            _original_handler(signum, frame)
            return

        if _count in callbacks:
            callbacks[_count]()

    signal.signal(signal.SIGINT, _handler)

    try:
        yield
    finally:
        _release()
