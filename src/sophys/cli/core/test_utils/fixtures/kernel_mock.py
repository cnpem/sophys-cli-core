import pytest

from unittest.mock import patch

import IPython
from IPython.terminal.interactiveshell import TerminalInteractiveShell
from IPython.testing import globalipapp

from sophys.cli.core.__main__ import create_kernel
from sophys.cli.core.http_utils import RemoteSessionHandler
from sophys.cli.core.magics import add_to_namespace, NamespaceKeys
from sophys.cli.core.magics.tools_magics import HTTPMagics


@pytest.fixture(scope="session")
def http_server_uri():
    return "http://mocked_http_session.lnls.br"


@pytest.fixture(scope="session")
def no_auth_session_handler(http_server_uri):
    return RemoteSessionHandler(http_server_uri, disable_authentication=True)


@pytest.fixture(scope="session", params=[(False, False, False, True), (False, True, True, True)])
def ipython_app(request, no_auth_session_handler):
    ip: TerminalInteractiveShell = globalipapp.start_ipython() or globalipapp.get_ipython()

    _, kwargs = create_kernel(*request.param)
    ip.push(kwargs["user_ns"])

    patch.object(IPython, "get_ipython", globalipapp.get_ipython)
    ip.extension_manager.load_extension("sophys.cli.core.base_configuration")

    ip.register_magics(HTTPMagics)

    add_to_namespace(NamespaceKeys.REMOTE_SESSION_HANDLER, no_auth_session_handler, ipython=ip)

    return ip, request.param


@pytest.fixture(scope="function")
def ip_with_params(ipython_app) -> tuple[TerminalInteractiveShell, tuple]:
    yield ipython_app


@pytest.fixture(scope="function")
def ip(ipython_app) -> TerminalInteractiveShell:
    def run_magic(magic_name, line):
        ns = {**locals(), **ip.user_ns}
        exec("ip.run_line_magic(magic_name, line)", globals(), ns)

    ip = ipython_app[0]
    ip.run_magic = run_magic
    yield ip


