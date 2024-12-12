from __future__ import annotations

import atexit
import functools
import getpass
import logging
import threading
import time
import typing

from contextlib import contextmanager
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from bluesky_queueserver_api.comm_base import HTTPClientError, HTTPRequestError, RequestParameterError, RequestTimeoutError
from bluesky_queueserver_api.http import REManagerAPI as RM_HTTP_Sync
from bluesky_queueserver_api.console_monitor import _ConsoleMonitor


# https://blueskyproject.io/bluesky-queueserver/re_manager_api.html#status
class RM(RM_HTTP_Sync):
    """
    RunEngine Manager class with improved support for LSP completion.

    It simply wraps the base functions in processors that add the data
    to structured data classes.
    """
    @dataclass(init=False)
    class UIDs:
        running_item: typing.Optional[str]
        """UID of the currently running plan or None if no plan is currently running."""
        run_list: str
        """UID of the list of the active runs."""

        plan_queue: str
        """UID which is updated each time the contents of the queue is changed."""
        plan_history: str
        """UID which is updated each time the contents of the history is changed."""

        task_results: str
        """UID of the dictionary of task results."""

        plans_allowed: str
        """UID for the list of allowed plans."""
        devices_allowed: str
        """UID for the list of allowed devices."""

        plans_existing: str
        """UID for the list of existing plans in RE Worker namespace."""
        devices_existing: str
        """UID for the list of existing devices in RE Worker namespace."""

        lock_info: str

    class QueueMode:
        loop: bool
        ignore_failures: bool

    class ManagerState(StrEnum):
        Initializing = "initializing"
        """RE Manager is initializing (the RE Manager is starting or restarting)."""
        Idle = "idle"
        """RE Manager is idle and ready to execute requests."""
        Paused = "paused"
        """A plan was paused and Run Engine is in the paused state."""

        StartingQueue = "starting_queue"
        """Preparing to execute the queue."""
        ExecutingQueue = "executing_queue"
        """Queue is being executed."""

        ExecutingTask = "executing_task"
        """A foreground task (function or script) is being executed."""

        CreatingEnvironment = "creating_environment"
        """RE Worker environment is in the process of being created."""
        ClosingEnvironment = "closing_environment"
        """RE Worker environment is in the process of being closed (safe)."""
        DestroyingEnvironment = "destroying_environment"
        """RE Worker environment is in the process of being destroyed (emergency)."""

    class WorkerEnvironmentState(StrEnum):
        Initializing = "initializing"
        Failed = "failed"
        Idle = "idle"

        ExecutingPlan = "executing_plan"
        ExecutingTask = "executing_task"

        Closing = "closing"
        Closed = "closed"

    @dataclass(init=False)
    class Status(dict):
        version: str

        num_items_in_queue: int
        num_items_in_history: int

        uids: RM.UIDs

        manager_state: RM.ManagerState
        re_state: typing.Optional[str]

        worker_environment_exists: bool
        worker_environment_state: RM.WorkerEnvironmentState

        queue_mode: RM.QueueMode

        autostart_enabled: bool
        stop_pending: bool
        pause_pending: bool

    def status(self, *, reload=False):
        sts_d = super().status(reload=False)

        sts = self.Status(**sts_d)

        sts.version = sts_d["msg"]
        sts.num_items_in_queue = sts_d["items_in_queue"]
        sts.num_items_in_history = sts_d["items_in_history"]

        sts.uids = self.UIDs()
        sts.uids.running_item = sts_d["running_item_uid"]
        sts.uids.run_list = sts_d["run_list_uid"]
        sts.uids.plan_queue = sts_d["plan_queue_uid"]
        sts.uids.plan_history = sts_d["plan_history_uid"]
        sts.uids.task_results = sts_d["task_results_uid"]
        sts.uids.plans_allowed = sts_d["plans_allowed_uid"]
        sts.uids.devices_allowed = sts_d["devices_allowed_uid"]
        sts.uids.plans_existing = sts_d["plans_existing_uid"]
        sts.uids.devices_existing = sts_d["devices_existing_uid"]
        sts.uids.lock_info = sts_d["lock_info_uid"]

        sts.queue_mode = self.QueueMode()
        sts.queue_mode.loop = sts_d["plan_queue_mode"]["loop"]
        sts.queue_mode.ignore_failures = sts_d["plan_queue_mode"]["ignore_failures"]

        sts.manager_state = sts_d["manager_state"]
        sts.re_state = sts_d["re_state"]
        sts.worker_environment_exists = sts_d["worker_environment_exists"]
        sts.worker_environment_state = sts_d["worker_environment_state"]
        sts.autostart_enabled = sts_d["queue_autostart_enabled"]
        sts.stop_pending = sts_d["queue_stop_pending"]
        sts.pause_pending = sts_d["pause_pending"]

        return sts


class RemoteSessionHandler(threading.Thread):
    """
    Utility class for keeping authentication state for HTTPServer.

    Calling `start()` on an object of this class will keep refreshing the access tokens
    for as long as it runs. Call `close()` then to stop it, closing the manager connection.

    You can use the `disable_authentication` keyword argument in the constructor to avoid
    asking the user to authenticate whenever they aren't already, if you need to.
    This will make all API calls come from UNAUTHENTICATED_PUBLIC, and the server role
    restrictions apply. You can still use the `ask_for_authentication` method if you want
    to manually authenticate the user.
    """

    CANCEL_CACHE_TIME = 1.0
    """The amount of time to wait between consecutive authorization attempts when cancelling."""

    @functools.wraps(threading.Thread.__init__)
    def __init__(self, http_server_uri, *, disable_authentication: bool = False):
        super().__init__(daemon=True)

        self._logger = logging.getLogger("sophys_cli.http")
        self._manager = RM(http_server_uri=http_server_uri, http_auth_provider="ldap/token")

        self._enable_authentication = not disable_authentication
        if disable_authentication:
            self._logger.warning("Running the remote session handler without authentication enabled. Server restriction to unauthenticated users will apply.")

        self._running = False
        self._authorized = False

        self._last_session_time = 0
        self._last_refresh_time = 0
        self._total_session_token_valid_time = 0
        self._total_refresh_token_valid_time = 0

        self._last_cancel_time = 0

    def get_authorized_manager(self) -> RM:
        """Retrieve the REManager instance, asking for credential if needed."""
        if not self._authorized and self._enable_authentication:
            # If we cancelled just a short while ago, consider this attempt as a cancel too.
            if time.monotonic() - self._last_cancel_time > self.CANCEL_CACHE_TIME:
                self.ask_for_authentication()
        return self._manager

    def ask_for_authentication(self):
        """
        Ask the user for their credentials, to authenticate on HTTPServer.

        Returns
        -------
        bool
            Whether the authorization was successful (True) or cancelled by the user (False).
        """
        print("Authentication is required to proceed! Please enter your credentials. [Ctrl-C to cancel]")

        response = None

        while response is None:
            try:
                username = input("Username: ")
                password = getpass.getpass()
            except (KeyboardInterrupt, EOFError):
                print()
                self._logger.info("Authentication cancelled.")
                self._last_cancel_time = time.monotonic()
                return False

            try:
                self._last_session_time = time.monotonic()
                self._last_refresh_time = self._last_session_time

                response = self._manager.login(username=username, password=password)

                self._total_session_token_valid_time = response["expires_in"]
                self._total_refresh_token_valid_time = response["refresh_token_expires_in"]
            except (HTTPClientError, RequestParameterError) as e:
                self._logger.error("  Failed to authenticate! Try again.\n    %s\n", "    \n".join(e.args))

        self._authorized = True

        return True

    def run(self):
        atexit.register(self.close)

        self._running = True

        while self._running:
            # Wait until the user asks for something and authenticates.
            if not self._authorized:
                self._logger.debug("Waiting for authorization...")
                while not self._authorized:
                    time.sleep(1.0)

            time_until_next_refresh = self._total_session_token_valid_time - (time.monotonic() - self._last_refresh_time)
            time_until_next_refresh -= 1  # Give a bit of leeway

            self._logger.debug("Sleeping until next refresh, in %fs...", time_until_next_refresh)
            time.sleep(abs(time_until_next_refresh))

            time_until_next_session = self._total_refresh_token_valid_time - (time.monotonic() - self._last_session_time)
            if time_until_next_session < 1:  # Some leeway, could be 0 too
                self._logger.debug("Session is about to expire, will wait for user input.")
                self._authorized = False  # Authenticate the next time the user asks for the manager
                continue

            self._logger.debug("Refreshing session...")
            try:
                _t = time.monotonic()

                response = self._manager.session_refresh()

                self._last_refresh_time = _t
                self._total_session_token_valid_time = response["expires_in"]
                self._total_refresh_token_valid_time = response["refresh_token_expires_in"]
            except RequestParameterError:
                self._logger.debug("Failed to refresh session due to missing refresh token!")
                self._authorized = False
            except Exception:
                self._logger.debug("Failed to refresh session with some (unknown) error.")
                pass

    def close(self):
        self._logger.debug("Logging out and closing the manager...")
        try:
            self._manager.logout()
        except HTTPRequestError:
            pass
        self._manager.close()
        self._running = False


@contextmanager
def monitor_console(console_monitor: _ConsoleMonitor, on_line_received: typing.Optional[Callable[[str], None]] = None):
    """
    Context manager for monitoring remote activity via the console
    on a background thread.

    Parameters
    ----------
    console_monitor : ConsoleMonitor
        The queueserver-api object connected to the appropriate console feed.
    on_line_received : callable of str, optional
        A user-supplied callback to receive messages from the console monitor.
        By default, it will call `print` on the message, with a gray foreground color.
    """
    _logger = logging.getLogger("sophys_cli.monitor_console")

    def default_pretty_print_console_log(x):
        # Print with a gray font color
        print(f"\033[38:5:248m{x}\033[0m")
    if on_line_received is None:
        on_line_received = default_pretty_print_console_log

    close = False

    def background_job():
        nonlocal close

        while not close:
            try:
                msg = console_monitor.next_msg(timeout=0.2)
                on_line_received(msg["msg"].strip())
            except RequestTimeoutError:
                pass

    _logger.debug("Starting monitoring console %s...", repr(console_monitor))

    console_monitor.clear()
    _bg = threading.Thread(target=background_job)
    _bg.start()
    console_monitor.enable()

    _logger.debug("Started monitoring console %s.", repr(console_monitor))
    try:
        yield
    finally:
        _logger.debug("Closing console monitor %s...", repr(console_monitor))
        console_monitor.disable()
        close = True
        _bg.join()

        _logger.debug("Console monitor %s closed.", repr(console_monitor))
