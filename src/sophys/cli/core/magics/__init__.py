import enum
import functools

from contextlib import contextmanager

import IPython

from .. import BANNER_NAME_EXTEND
from ..http_utils import RemoteSessionHandler


class NamespaceKeys(enum.StrEnum):
    BEST_EFFORT_CALLBACK = "BEC"
    BLACKLISTED_DESCRIPTIONS = "__blacklisted_magic_descriptions"
    COLORIZED_OUTPUT = "_COLORIZED"
    DATABROKER = "DB"
    DEBUG_MODE = "DEBUG"
    DEVICES = "D"
    EXTENSION_NAME = "EXTENSION"
    KAFKA_BOOTSTRAP = "_kafka_bootstrap"
    KAFKA_MONITOR = "KAFKA_MON"
    KAFKA_TOPIC = "_kafka_topic"
    LAST_DATA = "LAST"
    LOCAL_DATA_SOURCE = "__local_data_source"
    LOCAL_MODE = "LOCAL_MODE"
    PERSISTENT_METADATA = "__persistent_metadata"
    PLANS = "P"
    REMOTE_SESSION_HANDLER = "_remote_session_handler"
    REMOTE_DATA_SOURCE = "__data_source"
    RUN_ENGINE = "RE"
    TEST_MODE = "TEST_MODE"
    TEST_DATA = "__test_data"


def add_to_namespace(key: NamespaceKeys, value, ipython=None, _globals=None):
    if _globals is not None:
        _globals.update({key: value})
        return

    if ipython is None:
        ipython = IPython.get_ipython()

    ipython.push({key: value})


def get_from_namespace(key: NamespaceKeys, default=None, ipython=None, ns=None):
    if ipython is None and ns is None:
        ipython = IPython.get_ipython()
    if ns is None:
        ns = ipython.user_ns

    return ns.get(key, default)


def in_debug_mode(local_ns):
    return get_from_namespace(NamespaceKeys.DEBUG_MODE, ns=local_ns)


def get_color(color: str) -> str:
    if get_from_namespace(NamespaceKeys.COLORIZED_OUTPUT, default=True):
        return color
    return ""


@functools.lru_cache(maxsize=2)
def render_custom_magics(ipython, consider_blacklist: bool = True):
    """Render custom magic descriptions."""
    blacklist = set()
    if consider_blacklist:
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
                    reset_color = get_color("\033[0m")
                    render.append(f"{color}{name:<{BANNER_NAME_EXTEND}}: {desc}{reset_color}")

    # Add extra spacing between commands of different colors
    from itertools import pairwise
    _extra_index = 0
    for (_, fst), (pos, snd) in pairwise(_rendered_magics):
        fst_d = fst.description()[-1]
        snd_d = snd.description()[0]

        colors_are_the_same = fst_d[-1] == snd_d[-1]
        has_extra_space = render[pos] == "" or (len(render) > (pos + 1) and render[pos + 1] == "")
        if not colors_are_the_same and not has_extra_space:
            render.insert(pos + _extra_index, "")
            _extra_index += 1

    render.append("")
    render.append("")
    return render


def setup_remote_session_handler(ipython, address: str, *, disable_authentication: bool = False):
    """
    Properly configure the manager for remote session tokens.

    This will also immediately ask for user credentials for authentication, if it
    is enabled, and will update the local cache of devices and plan names upon
    successful connection and authentication.

    Parameters
    ----------
    address : str
        The HTTP address of httpserver we're connecting to.
    disable_authentication : bool, optional
        Controls whether we'll ask user credentials and keep session tokens on
        HTTP requests. This will only work properly if httpserver is configured for that.
        Disabled by default.
    """
    _remote_session_handler = RemoteSessionHandler(address, disable_authentication=disable_authentication)
    _remote_session_handler.start()

    if not disable_authentication:
        _remote_session_handler.ask_for_authentication()

    add_to_namespace(NamespaceKeys.REMOTE_SESSION_HANDLER, _remote_session_handler, ipython)

    try:
        ipython.run_line_magic("reload_devices", "")
        ipython.run_line_magic("reload_plans", "")
    except Exception:
        print(f"Could not connect to httpserver at address '{address}'.")


def setup_plan_magics(
        ipython,
        sophys_name: str,
        plan_whitelist: dict,
        mode_of_operation,
        post_submission_callbacks: list[callable] | None = None,
        exception_handlers: dict[type(Exception), callable] | None = None,
        ):
    """
    Configure plan magics for the application.

    Parameters
    ----------
    ipython : InteractiveShellApp
        The IPython instance of this application.
    sophys_name : str
        Name of this extension, as its shorthand (i.e. xyz in sophys-xyz).
    plan_whitelist : PlanWhitelist
        Whitelist object of plans allowed to be created magics for, and their
        configurations.
    mode_of_operation : ModeOfOperation
        Whether we're in local or remote mode.
    post_submission_callbacks : list of callables, optional
        Functions to call right after submitting a plan successfully. This
        allows us to provide custom feedback and additional behavior to the
        user.

        These callables can also return a boolean indicating whether the
        submission actually failed or was successful.
    exception_handler : dict of Exception types to callables, optional
        Functions to call when different exceptions are raised by the plan
        submission code. This can handle errors in a way specific to the
        environment being used.

        The callbacks receive the original exception object, and the local
        namespace, and return an object of ExceptionHandlerReturnValue
        indicating how to proceed.
    """
    from .plan_magics import register_magic_for_plan, get_plans, RealMagics

    if post_submission_callbacks is None:
        post_submission_callbacks = []

    if exception_handlers is None:
        exception_handlers = {}

    for plan_information, plan in get_plans(sophys_name, plan_whitelist):
        register_magic_for_plan(plan, plan_information, mode_of_operation, post_submission_callbacks, exception_handlers)
    ipython.register_magics(RealMagics)


@contextmanager
def handle_ctrl_c_signals(callbacks: dict | None = None, max_signal_count: int = 9, ignore_original_handler: bool = False):
    """
    Context manager for intercepting and handling SIGINTs in a clean way.

    Parameters
    ----------
    callbacks : dict, optional
        Callbacks in the form (Ctrl+C count) -> (Callable) for making stuff when getting SIGINTs.
    max_signal_count : int, optional
        Maximum number of SIGINTs to handle before returning to the original handler. Defaults to 10.
    ignore_original_handler : bool, optional
        Whether to ignore the original handler when reaching `max_signal_count` interrupts,
        doing nothing in its place. Defaults to False.
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

        if _count in callbacks:
            callbacks[_count]()

        if _count > max_signal_count and not _released:
            _release()

            _original_handler(signum, frame)

            return

    signal.signal(signal.SIGINT, _handler)

    if ignore_original_handler:
        try:
            yield
        except KeyboardInterrupt:
            pass
        finally:
            _release()
    else:
        try:
            yield
        finally:
            _release()
