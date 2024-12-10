from argparse import ArgumentParser
from pathlib import Path

from traitlets.config import Config

from . import BANNER_NAME_EXTEND
from .magics import NamespaceKeys


variables_desc = {
    "D": "The list of available devices (to the current user).",
    "P": "The list of available plans (to the current user).",
    "RE": "The Bluesky run engine.",
    "DB": "A databroker instance containing the most recent runs data and metadata.",
    "LAST": "The last run data, as a Pandas Dataframe.",
    "BEC": "The BestEffortCallback instance hooked up to the run data.",
}


def create_banner_text(args):
    banner_variables = ["D", "P", "DB", "LAST", "BEC"]
    if args.local:
        banner_variables.append("RE")
    banner_variables.sort()

    banner_lines = []
    if len(banner_variables) > 0:
        banner_lines.append("The custom available variables are:")
        for var in banner_variables:
            banner_lines.append(f"{var:<{BANNER_NAME_EXTEND}}: {variables_desc[var]}")
        banner_lines.append("")

    if args.local:
        banner_lines += [
            "The custom available modules are:",
            f"{"bp":<{BANNER_NAME_EXTEND}}: bluesky.plans",
            f"{"bps":<{BANNER_NAME_EXTEND}}: bluesky.plan_stubs",
            "",
        ]

    return "\n".join(banner_lines)


def entrypoint():
    parser = ArgumentParser()
    parser.add_argument("extension", help="The extension to load the configuration from.")
    parser.add_argument("--debug", help="Configure debug mode, with more verbose logging and error messgaes.", action="store_true")
    parser.add_argument("--local", help="Use a local RunEngine instead of communicating with HTTPServer (implies --test).", action="store_true")
    parser.add_argument("--test", help="Setup testing configurations to test the tool without interfering with production configured parameters.", action="store_true")
    parser.add_argument("--nocolor", help="Remove color codes from rich output.", action="store_false")
    args = parser.parse_args()

    extension = args.extension

    # Documentation: https://ipython.readthedocs.io/en/stable/config/options/kernel.html
    ipy_config = Config()

    ipy_config.Application.logging_config = {
        "formatters": {
            "default": {
                "format": "[%(asctime)s] [%(levelname)s] - %(message)s",
                "datefmt": "%H:%M:%S",
            },
            "debug": {
                "format": "[%(asctime)s] [%(name)s %(levelname)s] - %(message)s",
            }
        },
        "handlers": {
            "print": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "default" if not args.debug else "debug",
            },
        },
        "loggers": {
            "kafka": {
                "level": "WARNING" if not args.debug else "INFO",
                "handlers": ["print"],
            },
            "kafka.coordinator.consumer": {
                "level": "ERROR",
                "handlers": ["print"],
            },
            "sophys_cli": {
                "level": "INFO" if not args.debug else "DEBUG",
                "handlers": ["print"],
            },
        }
    }

    ipy_config.InteractiveShellApp.exec_files = [str(Path(__file__).parent / "pre_execution.py")]

    ipy_config.InteractiveShell.banner2 = create_banner_text(args)

    ipy_config.InteractiveShellApp.extensions = [f"sophys.cli.extensions.{extension}"]

    ipy_config.TerminalInteractiveShell.confirm_exit = False

    args.test = args.test or args.local

    import IPython
    init_ns = {
        "EXTENSION": extension,
        NamespaceKeys.DEBUG_MODE: args.debug,
        NamespaceKeys.LOCAL_MODE: args.local,
        NamespaceKeys.TEST_MODE: args.test,
        NamespaceKeys.COLORIZED_OUTPUT: args.nocolor,
    }
    IPython.start_ipython(argv=[], config=ipy_config, user_ns=init_ns)

