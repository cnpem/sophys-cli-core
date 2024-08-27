import logging
import subprocess

from abc import ABC, abstractmethod

from IPython import get_ipython
from IPython.core.magic import Magics, magics_class, line_magic, needs_local_scope


class ToolMagicBase(ABC):
    @staticmethod
    @abstractmethod
    def description() -> list[str]:
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

        if local_ns["DEBUG"]:
            proc = subprocess.Popen(command_line, **kwargs)
        else:
            proc = subprocess.Popen(command_line, **kwargs,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        logging.info(f"Running {command_line} in a new process... (PID={proc.pid})")

    @staticmethod
    def description():
        tools = []
        tools.append("kbl: \t\tOpen kafka-bluesky-live")
        return tools


@magics_class
class HTTPMagics(Magics):
    @line_magic
    @needs_local_scope
    def reload_devices(self, line, local_ns):
        remote_session_handler = local_ns.get("_remote_session_handler", None)
        if remote_session_handler is None:
            logging.debug("No '_remote_session_handler' variable present in local_ns.")
            return

        res = remote_session_handler.get_authorized_manager().devices_allowed()
        if not res["success"]:
            logging.warning("Failed to request available devices: %s", res["msg"])
        else:
            # We need to modify the original one, not the 'local_ns', which is a copy.
            get_ipython().push({"D": set(res["devices_allowed"])})

    @line_magic
    @needs_local_scope
    def reload_plans(self, line, local_ns):
        remote_session_handler = local_ns.get("_remote_session_handler", None)
        if remote_session_handler is None:
            logging.debug("No '_remote_session_handler' variable present in local_ns.")
            return

        res = remote_session_handler.get_authorized_manager().plans_allowed()
        if not res["success"]:
            logging.warning("Failed to request available plans: %s", res["msg"])
        else:
            if not hasattr(self, "plan_whitelist"):
                logging.warning("No plan whitelist has been set. Using the empty set.")
                self.plan_whitelist = set()
            # We need to modify the original one, not the 'local_ns', which is a copy.
            get_ipython().push({"P": set(res["plans_allowed"]) & set(self.plan_whitelist)})

    @staticmethod
    def description():
        tools = []
        tools.append("reload_devices: \tReload the available devices list (D).")
        tools.append("reload_plans: \tReload the available plans list (P).")
        return tools
