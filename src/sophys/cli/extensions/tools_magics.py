import logging
import subprocess

from IPython.core.magic import Magics, magics_class, line_magic, needs_local_scope


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

        proc = subprocess.Popen(command_line,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        logging.info(f"Running {command_line} in a new process... (PID={proc.pid})")
