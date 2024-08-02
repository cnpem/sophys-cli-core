import subprocess

from IPython.core.magic import Magics, magics_class, line_magic


@magics_class
class KBLMagics(Magics):
    @line_magic
    def kbl(self, line):
        """Run kafka-bluesky-live in a subprocess."""
        subprocess.Popen(["kbl", *line.split(" ")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
