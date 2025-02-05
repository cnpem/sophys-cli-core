import logging
import subprocess
import typing

from abc import ABC, abstractmethod
from contextlib import contextmanager

from IPython import get_ipython
from IPython.core.magic import Magics, magics_class, line_magic, needs_local_scope

from . import in_debug_mode, render_custom_magics, NamespaceKeys, get_from_namespace, get_color, handle_ctrl_c_signals
from ..http_utils import RM, monitor_console


class ToolMagicBase(ABC):
    @staticmethod
    @abstractmethod
    def description() -> list[tuple[str, str] | tuple[str, str, str]]:
        """
        Descriptions are of either of the following:
            2-tuple: (name, description)
            3-tuple: (name, description, color)

        Colors are ANSI color codes. For reference:
        https://talyian.github.io/ansicolors/
        """
        pass


@magics_class
class KBLMagics(Magics):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._logger = logging.getLogger("sophys_cli.tools")

    @line_magic
    @needs_local_scope
    def kbl(self, line, local_ns):
        """Run kafka-bluesky-live in a subprocess."""
        if len(line) > 0:
            command_line = ["kbl", *line.split(" ")]
        else:
            default_bss = local_ns["default_bootstrap_servers"]()
            default_tn = get_from_namespace(NamespaceKeys.KAFKA_TOPIC)
            command_line = ["kbl", default_tn, "--bootstrap-servers", " ".join(default_bss)]

        kwargs = {"start_new_session": True}

        if in_debug_mode(local_ns):
            proc = subprocess.Popen(command_line, **kwargs)
        else:
            proc = subprocess.Popen(command_line, **kwargs,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        self._logger.info(f"Running {command_line} in a new process... (PID={proc.pid})")

    @staticmethod
    def description():
        tools = []
        tools.append(("kbl", "Open kafka-bluesky-live", get_color("\x1b[38;5;82m")))
        return tools


@magics_class
class MiscMagics(Magics):
    @line_magic
    @needs_local_scope
    def cs(self, line, local_ns):
        ipython = get_ipython()

        # Variables
        print(ipython.banner2)
        # Magics
        print("\n".join(render_custom_magics(ipython)))

    @line_magic
    @needs_local_scope
    def show_md(self, line, local_ns):
        print("Configured metadata:")
        persistent_metadata = get_from_namespace(NamespaceKeys.PERSISTENT_METADATA, ns=local_ns)
        persistent_metadata.pretty_print_entries()

    @line_magic
    @needs_local_scope
    def add_md(self, line, local_ns):
        persistent_metadata = get_from_namespace(NamespaceKeys.PERSISTENT_METADATA, ns=local_ns)

        args = [k for i in line.split(' ') for k in i.split('=')]
        for i in range(0, len(args), 2):
            print(f"Setting metadata key '{args[i]}' to '{args[i+1]}'.")
            persistent_metadata.add_entry(args[i], args[i+1])

    @line_magic
    @needs_local_scope
    def remove_md(self, line, local_ns):
        persistent_metadata = get_from_namespace(NamespaceKeys.PERSISTENT_METADATA, ns=local_ns)

        keys = line.split(' ')
        for key in keys:
            print(f"Removing entry '{key}'.")
            persistent_metadata.remove_entry(key)

    @staticmethod
    def description():
        tools = []
        tools.append(("cs", "Print this help page, with all custom functionality summarized."))
        tools.append(("", ""))
        tools.append(("show_md", "Print all non-default configured metadata.", get_color("\x1b[38;5;218m")))
        tools.append(("add_md", "Add a new metadata to the internal state, which will be applied to all next runs.", get_color("\x1b[38;5;218m")))
        tools.append(("remove_md", "Remove a custom metadata entry, reverting for its normal state.", get_color("\x1b[38;5;218m")))
        return tools


@magics_class
class HTTPMagics(Magics):
    def __init__(self, *args, **kwargs):
        """
        IPython magics for httpserver interaction.

        Attributes
        ----------
        additional_state : list of callables, optional
            A list of additional logic to render when calling the 'query_state' magic.
            The callbacks receive no arguments, and must return a string with the state rendered in it.

            For example:
                def my_custom_state() -> str:
                    render = "My state:" + "\n"
                    render += "  State: Cool" + "\n"
                    return render

                ipython = get_ipython()
                ipython.register_magics(HTTPMagics)
                ipython.magics_manager.registry["HTTPMagics"].additional_state = [my_custom_state]
                ...
        """
        super().__init__(*args, **kwargs)

        self._logger = logging.getLogger("sophys_cli.tools")

    @classmethod
    def get_manager(cls, local_ns=None, logger=None):
        """Configure 'local_ns' to None if using nested magics."""
        remote_session_handler = get_from_namespace(NamespaceKeys.REMOTE_SESSION_HANDLER, ns=local_ns)
        if remote_session_handler is None:
            if logger is not None:
                logger.debug("No '_remote_session_handler' variable present in local_ns.")
                logger.debug("local_ns contents: %s", " ".join(local_ns.keys()))
            return

        return remote_session_handler.get_authorized_manager()

    @classmethod
    def get_history(self, manager, logger) -> typing.Sequence[tuple[int, dict]] | None:
        """Retrieve the plan execution history, from most recent to oldest entries."""
        res = manager.history_get()
        if not res["success"]:
            logger.warning("Failed to query the history: %s", res["msg"])
            return

        if len(res["items"]) == 0:
            print("History is currently empty.")
            return

        return enumerate(reversed(res["items"]))

    @classmethod
    def _reload_environment(cls, manager, force: bool, logger):
        """Reload the queueserver worker environment."""
        with monitor_console(manager.console_monitor):
            env_exists = manager.status()["worker_environment_exists"]
            if env_exists:
                if force:
                    print("Destroying environment...")
                    res = manager.environment_destroy()
                else:
                    print("Closing environment...")
                    res = manager.environment_close()

                if not res["success"]:
                    logger.warning("Failed to request environment closure: %s", res["msg"])
                    return

                manager.wait_for_idle()

            print("Opening environment...")
            res = manager.environment_open()
            if not res["success"]:
                logger.warning("Failed to request environment opening: %s", res["msg"])
                return

            manager.wait_for_idle()

    def _reload_devices(self, manager):
        res = manager.devices_allowed()
        if not res["success"]:
            self._logger.warning("Failed to request available devices: %s", res["msg"])
        else:
            self._logger.debug("Upstream allowed devices: %s", " ".join(res["devices_allowed"].keys()))

            # We need to modify the original one, not the 'local_ns', which is a copy.
            get_ipython().push({"D": set(res["devices_allowed"])})

    def _reload_plans(self, manager):
        res = manager.plans_allowed()
        if not res["success"]:
            self._logger.warning("Failed to request available plans: %s", res["msg"])
        else:
            if not hasattr(self, "plan_whitelist"):
                self._logger.warning("No plan whitelist has been set. Using the empty set.")
                self.plan_whitelist = set()

            self._logger.debug("Upstream allowed plans: %s", " ".join(res["plans_allowed"].keys()))

            # We need to modify the original one, not the 'local_ns', which is a copy.
            get_ipython().push({"P": self.plan_whitelist & set(res["plans_allowed"])})

    @line_magic
    def wait_for_idle(self, line):
        manager = self.get_manager(logger=self._logger)
        if manager is None:
            return

        print("")
        print("You are now in processing mode.")
        print("A plan is running, and you can control it with the following:")

        if line != "soft":
            print("  Ctrl+C: Stop immediately the plan.")
        else:
            print("  Ctrl+C: Exit this mode without sending any commands.")

        print("")

        tried_to_stop = False

        def first_time_callback():
            nonlocal tried_to_stop
            tried_to_stop = True

            if line != "soft":
                print("")
                self.stop(line, None)

        def last_time_callback():
            print()
            print("Leaving the waiting prompt without waiting for stop command to finish.")

        with handle_ctrl_c_signals({1: first_time_callback, 10: last_time_callback}, ignore_original_handler=True):
            manager.wait_for_idle()

        if not tried_to_stop:
            history_items = self.get_history(manager, logger=self._logger)
            if history_items is None:
                print("The execution history is empty??? Something has gone terribly wrong!")
                return

            last_item = next(history_items)[1]["result"]

            if last_item["exit_status"] != "completed":
                print("The plan has failed!")

                if len(msg := last_item["msg"]) != 0:
                    print(f"Exit message: {msg}")

                return False

    @line_magic
    @needs_local_scope
    def stop(self, line, local_ns):
        manager = self.get_manager(local_ns, logger=self._logger)
        if manager is None:
            return

        state = manager.status()

        if state["queue_stop_pending"]:
            manager.wait_for_idle()
            print("Plan stopped successfully.")
            return

        if state["manager_state"] != "paused":
            self.pause(line, local_ns)

        res = manager.re_stop()
        if not res["success"]:
            self._logger.warning("Failed to stop plan execution: %s", res["msg"])
            return

        manager.wait_for_idle_or_paused()
        print("Plan stopped successfully.")

    @line_magic
    @needs_local_scope
    def pause(self, line, local_ns):
        """https://blueskyproject.io/bluesky-queueserver-api/generated/bluesky_queueserver_api.zmq.REManagerAPI.re_pause.html"""
        if line == "":
            line = "immediate"

        manager = self.get_manager(local_ns, logger=self._logger)
        if manager is None:
            return

        print(f"{line.capitalize()} plan pause requested.")

        state = manager.status()

        if state["manager_state"] == "paused":
            print("Plan paused successfully.")
            return

        if state["manager_state"] != "executing_queue":
            self._logger.warning("Failed to pause plan: No plan is running.")
            return

        res = manager.re_pause(option=line)
        if not res["success"]:
            self._logger.warning("Failed to pause plan execution: %s", res["msg"])
        else:
            manager.wait_for_idle_or_paused()
            print("Plan paused successfully.")

    @line_magic
    @needs_local_scope
    def resume(self, line, local_ns):
        manager = self.get_manager(local_ns, logger=self._logger)
        if manager is None:
            return

        res = manager.re_resume()
        if not res["success"]:
            self._logger.warning("Failed to resume plan execution: %s", res["msg"])
        else:
            manager.wait_for_idle_or_running()
            print("Plan resumed successfully.")

    @line_magic
    @needs_local_scope
    def reload_devices(self, line, local_ns):
        manager = self.get_manager(local_ns, logger=self._logger)
        if manager is None:
            return

        self._reload_devices(manager)

    @line_magic
    @needs_local_scope
    def reload_plans(self, line, local_ns):
        manager = self.get_manager(local_ns, logger=self._logger)
        if manager is None:
            return

        self._reload_plans(manager)

    @line_magic
    @needs_local_scope
    def query_state(self, line, local_ns):
        manager: RM = self.get_manager(local_ns, logger=self._logger)
        if manager is None:
            return

        def pretty_print_state(state: RM.Status):
            print()
            print(f"Version: {state.version}")
            print( "Running state:")  # noqa: E201
            print(f"  Manager: {state.manager_state}")
            print(f"  RunEngine: {state.re_state} (Exists: {state.worker_environment_exists} | State: {state.worker_environment_state})")
            print(f"  Items:  Queue ({state.num_items_in_queue}) | History ({state.num_items_in_history})")
            print( "Server configuration:")  # noqa: E201
            print(f"  Pause pending: {state.pause_pending} | Stop pending: {state.stop_pending}")
            print(f"  Autostart: {state.autostart_enabled}")
            print(f"  Loop: {state.queue_mode.loop}")
            print()

            if state.uids.running_item is not None:
                print("Running plan information:")

                res = manager.queue_get()
                if not res["success"]:
                    print(f"  Could not retrieve information about the running plan: {res['msg']}")
                    return

                running_item = res["running_item"]
                print(f"  Plan name: {running_item['name']}")
                print( "  Arguments:")  # noqa: E201

                args = ", ".join(str(i) for i in running_item["args"])
                print(f"   args: {args}")

                if "kwargs" in running_item:
                    kwargs = ", ".join("'{}' = {}".format(*i) for i in running_item["kwargs"].items())
                    print(f"   kwargs: {kwargs}")

                from time import strftime, localtime
                print( "  Run metadata:")  # noqa: E201
                print(f"    User: {running_item['user']}")
                print(f"    User group: {running_item['user_group']}")
                time_format = "%H:%M:%S (%d/%m/%Y)"
                start_time = strftime(time_format, localtime(running_item["properties"]["time_start"]))
                print(f"    Start time: {start_time}")

                print()

        try:
            res = manager.status()
        except Exception as e:
            self._logger.exception("An exception has occured when trying to query the server state:", *e.args)
        else:
            pretty_print_state(res)

        if hasattr(self, "additional_state"):
            for cb in self.additional_state:
                print(cb())
                print()

    @line_magic
    @needs_local_scope
    def reload_environment(self, line, local_ns):
        manager = self.get_manager(local_ns, logger=self._logger)
        if manager is None:
            return

        self._reload_environment(manager, "force" in line, self._logger)
        self._reload_devices(manager)
        self._reload_plans(manager)

    @line_magic
    @needs_local_scope
    def query_history(self, line, local_ns):
        def pretty_render_history_item(item: dict, index: int = 0) -> str:
            item_type = item["item_type"]

            if item_type == "plan":
                title_color = get_color("\x1b[48;5;16m\x1b[38;5;85m")
                if len(item["result"]["msg"]) != 0:
                    title_color = get_color("\x1b[48;5;0m\x1b[38;5;204m")

                render = [title_color + f"=-- Entry #{index}: Plan --=" + get_color("\033[0m")]
                render.append(f" Plan name: {item["name"]}")
                render.append( " Arguments")  # noqa: E201

                args = ", ".join(str(i) for i in item["args"])
                render.append(f"   args: {args}")

                if "kwargs" in item:
                    kwargs = ", ".join("'{}' = {}".format(*i) for i in item["kwargs"].items())
                    render.append(f"   kwargs: {kwargs}")

                render.append( " Run metadata")  # noqa: E201
                render.append(f"   User: {item["user"]}")
                render.append(f"   User group: {item["user_group"]}")

                render.append( " Run result")  # noqa: E201
                result = item["result"]

                render.append(f"   Exit status: {result["exit_status"]}")

                from time import strftime, localtime
                time_format = "%H:%M:%S (%d/%m/%Y)"
                start_time = strftime(time_format, localtime(result["time_start"]))
                stop_time = strftime(time_format, localtime(result["time_stop"]))
                duration = (result["time_stop"] - result["time_start"])
                render.append(f"   Time: {start_time} - {stop_time} (Duration: {duration:.3f}s)")

                render.append("")

                if len(uuids_raw := result["run_uids"]) != 0:
                    uuids = " ".join(uuids_raw)
                    render.append(f"   Run UUIDs: {uuids}")
                    scan_ids = " ".join(str(i) for i in result["scan_ids"])
                    render.append(f"   Scan IDs: {scan_ids}")

                if len(msg := result["msg"]) != 0:
                    render.append(f"   Exit message: {msg}")
                    traceback = "\n      ".join(result["traceback"].split("\n"))
                    render.append(f"   Traceback:\n      {traceback}")

                return "\n".join(render)

            return f"Unhandled item type '{item_type}'"

        manager = self.get_manager(local_ns, logger=self._logger)
        if manager is None:
            return

        history_items = self.get_history(manager, logger=self._logger)

        from IPython.core import page
        render = "queueserver history - More recent entries are at the top.\n"
        render += "  Press 'q' to exit this view.\n\n\n"
        render += "\n\n\n".join(pretty_render_history_item(item, i) for i, item in history_items)

        @contextmanager
        def disabled_bec():
            table_originally_enabled = False
            headings_originally_enabled = False
            baseline_originally_enabled = False

            bec = get_from_namespace(NamespaceKeys.BEST_EFFORT_CALLBACK, ns=local_ns)

            if bec is not None:
                table_originally_enabled = bec._table_enabled
                bec.disable_table()
                headings_originally_enabled = bec._heading_enabled
                bec.disable_heading()
                baseline_originally_enabled = bec._baseline_enabled
                bec.disable_baseline()

            try:
                yield
            finally:
                if bec is not None:
                    if table_originally_enabled:
                        bec.enable_table()
                    if headings_originally_enabled:
                        bec.enable_heading()
                    if baseline_originally_enabled:
                        bec.enable_baseline()

        with disabled_bec():
            page.page(render)

    @staticmethod
    def description():
        tools = []
        tools.append(("wait_for_idle", "Wait execution until the RunEngine returns to the Idle state. Use with 'soft' argument for no stopping controls.", get_color("\x1b[38;5;204m")))
        tools.append(("pause", "Request a pause for the currently executing plan.", get_color("\x1b[38;5;204m")))
        tools.append(("resume", "Request the currently paused plan to resume execution.", get_color("\x1b[38;5;204m")))
        tools.append(("stop", "Request the currently executing or paused plan to stop and quit execution.", get_color("\x1b[38;5;204m")))
        tools.append(("", ""))
        tools.append(("query_state", "Query the current server state.", get_color("\x1b[38;5;69m")))
        tools.append(("query_history", "Query the current item history, with their statuses.", get_color("\x1b[38;5;69m")))
        tools.append(("", ""))
        tools.append(("reload_devices", "Reload the available devices list (D).", get_color("\x1b[38;5;222m")))
        tools.append(("reload_plans", "Reload the available plans list (P).", get_color("\x1b[38;5;222m")))
        tools.append(("reload_environment", "Reload currently active environment. Open a new one if the current env is closed.", get_color("\x1b[38;5;222m")))
        return tools
