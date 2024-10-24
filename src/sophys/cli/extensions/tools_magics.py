import logging
import subprocess

from abc import ABC, abstractmethod

from IPython import get_ipython
from IPython.core.magic import Magics, magics_class, line_magic, needs_local_scope

from . import in_debug_mode, render_custom_magics
from ..http_utils import monitor_console


class ToolMagicBase(ABC):
    @staticmethod
    @abstractmethod
    def description() -> list[tuple[str, str]]:
        pass


@magics_class
class KBLMagics(Magics):
    @line_magic
    @needs_local_scope
    def kbl(self, line, local_ns):
        """Run kafka-bluesky-live in a subprocess."""
        if len(line) > 0:
            command_line = ["kbl", *line.split(" ")]
        else:
            default_bss = local_ns["default_bootstrap_servers"]()
            default_tn = local_ns["default_topic_names"]()[0]
            command_line = ["kbl", default_tn, "--bootstrap-servers", " ".join(default_bss)]

        kwargs = {"start_new_session": True}

        if in_debug_mode(local_ns):
            proc = subprocess.Popen(command_line, **kwargs)
        else:
            proc = subprocess.Popen(command_line, **kwargs,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        logging.info(f"Running {command_line} in a new process... (PID={proc.pid})")

    @staticmethod
    def description():
        tools = []
        tools.append(("kbl", "Open kafka-bluesky-live"))
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

    @staticmethod
    def description():
        tools = []
        tools.append(("cs", "Print this help page, with all custom functionality summarized."))
        tools.append(("", ""))
        return tools


@magics_class
class HTTPMagics(Magics):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._logger = logging.getLogger("sophys_cli.tools")

    def get_manager(self, local_ns=None):
        """Configure 'local_ns' to None if using nested magics."""
        if local_ns is None:
            local_ns = get_ipython().user_ns

        remote_session_handler = local_ns.get("_remote_session_handler", None)
        if remote_session_handler is None:
            self._logger.debug("No '_remote_session_handler' variable present in local_ns.")
            self._logger.debug("local_ns contents: %s", " ".join(local_ns.keys()))
            return

        return remote_session_handler.get_authorized_manager()

    @line_magic
    def wait_for_idle(self, line):
        manager = self.get_manager()
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

        try:
            manager.wait_for_idle()
        except KeyboardInterrupt:
            if line != "soft":
                print("")
                self.stop(line, None)

    @line_magic
    @needs_local_scope
    def stop(self, line, local_ns):
        manager = self.get_manager(local_ns)
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

        manager = self.get_manager(local_ns)
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
        manager = self.get_manager(local_ns)
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
        manager = self.get_manager(local_ns)
        if manager is None:
            return

        res = manager.devices_allowed()
        if not res["success"]:
            self._logger.warning("Failed to request available devices: %s", res["msg"])
        else:
            self._logger.debug("Upstream allowed devices: %s", " ".join(res["devices_allowed"].keys()))

            # We need to modify the original one, not the 'local_ns', which is a copy.
            get_ipython().push({"D": set(res["devices_allowed"])})

    @line_magic
    @needs_local_scope
    def reload_plans(self, line, local_ns):
        manager = self.get_manager(local_ns)
        if manager is None:
            return

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
    @needs_local_scope
    def query_state(self, line, local_ns):
        def pretty_print_state(state):
            print()
            print(f"Version: {state['msg']}")
            print( "Running state:")  # noqa: E201
            print(f"  Manager: {state['manager_state']}")
            print(f"  RunEngine: {state['re_state']} (Exists: {state['worker_environment_exists']} | State: {state['worker_environment_state']})")
            print(f"  Items:  Queue ({state['items_in_queue']}) | History ({state['items_in_history']})")
            print( "Server configuration:")  # noqa: E201
            print(f"  Pause pending: {state['pause_pending']} | Stop pending: {state['queue_stop_pending']}")
            print(f"  Autostart: {state["queue_autostart_enabled"]}")
            print(f"  Loop: {state['plan_queue_mode']['loop']}")
            print()

        manager = self.get_manager(local_ns)
        if manager is None:
            return

        res = manager.status()

        pretty_print_state(res)

    @line_magic
    @needs_local_scope
    def reload_environment(self, line, local_ns):
        manager = self.get_manager(local_ns)
        if manager is None:
            return

        with monitor_console(manager.console_monitor):
            env_exists = manager.status()["worker_environment_exists"]
            if env_exists:
                print("Closing environment...")
                res = manager.environment_close()
                if not res["success"]:
                    self._logger.warning("Failed to request environment closure: %s", res["msg"])
                    return

                manager.wait_for_idle()

            print("Opening environment...")
            res = manager.environment_open()
            if not res["success"]:
                self._logger.warning("Failed to request environment opening: %s", res["msg"])
                return

            manager.wait_for_idle()

    @line_magic
    @needs_local_scope
    def query_history(self, line, local_ns):
        def pretty_render_history_item(item: dict, index: int = 0) -> str:
            item_type = item["item_type"]

            if item_type == "plan":
                render = [f"=-- Entry #{index}: Plan --="]
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

        manager = self.get_manager(local_ns)
        if manager is None:
            return

        res = manager.history_get()
        if not res["success"]:
            self._logger.warning("Failed to query the history: %s", res["msg"])
            return

        if len(res["items"]) == 0:
            print("History is currently empty.")
            return

        from IPython.core import page
        render = "queueserver history - More recent entries are at the top.\n\n\n"
        it = enumerate(reversed(res["items"]))
        render += "\n\n\n".join(pretty_render_history_item(item, i) for i, item in it)
        page.page(render)

    @staticmethod
    def description():
        tools = []
        tools.append(("", ""))
        tools.append(("wait_for_idle", "Wait execution until the RunEngine returns to the Idle state. Use with 'soft' argument for no stopping controls."))
        tools.append(("pause", "Request a pause for the currently executing plan."))
        tools.append(("resume", "Request the currently paused plan to resume execution."))
        tools.append(("stop", "Request the currently executing or paused plan to stop and quit execution."))
        tools.append(("", ""))
        tools.append(("query_state", "Query the current server state."))
        tools.append(("query_history", "Query the current item history, with their statuses."))
        tools.append(("", ""))
        tools.append(("reload_devices", "Reload the available devices list (D)."))
        tools.append(("reload_plans", "Reload the available plans list (P)."))
        tools.append(("reload_environment", "Reload currently active environment. Open a new one if the current env is closed."))
        return tools
