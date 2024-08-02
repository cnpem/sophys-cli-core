from argparse import ArgumentParser
from pathlib import Path

from traitlets.config import Config


def entrypoint():
    parser = ArgumentParser()
    parser.add_argument("beamline", help="The beamline to load the configuration from.")
    args = parser.parse_args()

    beamline = args.beamline

    ipy_config = Config()

    ipy_config.InteractiveShellApp.exec_files = [str(Path(__file__).parent / "pre_execution.py")]

    ipy_config.InteractiveShell.banner2 = """
    The custom available variables are:
    BEAMLINE: The currently configured beamline.
    D:        The list of instantiated devices.
    RE:       The Bluesky run engine.


    The custom available modules are:
    bp:  bluesky.plans
    bps: bluesky.plan_stubs


"""

    ipy_config.InteractiveShellApp.extensions = [f"sophys.cli.extensions.{beamline}_ext"]

    ipy_config.TerminalInteractiveShell.confirm_exit = False

    import IPython
    IPython.start_ipython(argv=[], config=ipy_config, user_ns={"BEAMLINE": beamline})

