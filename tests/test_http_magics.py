import pytest

import asyncio

from pathlib import Path
from unittest.mock import patch

import IPython
from IPython.terminal.interactiveshell import TerminalInteractiveShell
from IPython.testing import globalipapp

from sophys.cli import core
from sophys.cli.core.__main__ import create_kernel
from sophys.cli.core.magics import get_from_namespace, add_to_namespace, NamespaceKeys
from sophys.cli.core.magics.tools_magics import HTTPMagics


@pytest.fixture(scope="session", params=[(False, False, False, True), (False, True, True, True)])
def ipython_app(request, no_auth_session_handler):
    ip: TerminalInteractiveShell = globalipapp.start_ipython() or globalipapp.get_ipython()

    _, kwargs = create_kernel(*request.param)
    ip.push(kwargs["user_ns"])

    patch.object(IPython, "get_ipython", globalipapp.get_ipython)
    code_obj = ip.find_user_code(str(Path(core.__file__).parent / "pre_execution.py"), py_only=True)
    asyncio.run(ip.run_code(code_obj))

    ip.register_magics(HTTPMagics)

    add_to_namespace(NamespaceKeys.REMOTE_SESSION_HANDLER, no_auth_session_handler, ipython=ip)

    return ip, request.param


@pytest.fixture(scope="function")
def ip_with_params(ipython_app) -> tuple[TerminalInteractiveShell, tuple]:
    yield ipython_app


@pytest.fixture(scope="function")
def ip(ipython_app) -> TerminalInteractiveShell:
    def run_magic(magic_name, line):
        locals().update(ip.user_ns)
        ip.run_line_magic(magic_name, line)

    ip = ipython_app[0]
    ip.run_magic = run_magic
    yield ip


def test_instantiate_app(ip_with_params):
    ip, kernel_params = ip_with_params

    # Defined in the starting ns
    assert get_from_namespace(NamespaceKeys.COLORIZED_OUTPUT, ipython=ip) is kernel_params[0]
    assert get_from_namespace(NamespaceKeys.LOCAL_MODE, ipython=ip) is kernel_params[1]
    assert get_from_namespace(NamespaceKeys.TEST_MODE, ipython=ip) is kernel_params[2]
    assert get_from_namespace(NamespaceKeys.DEBUG_MODE, ipython=ip) is kernel_params[3]

    # Defined in pre_execution.py
    from bluesky.callbacks.best_effort import BestEffortCallback
    assert isinstance(get_from_namespace(NamespaceKeys.BEST_EFFORT_CALLBACK, ipython=ip), BestEffortCallback)


def test_get_manager(ip):
    assert get_from_namespace(NamespaceKeys.REMOTE_SESSION_HANDLER, ipython=ip) is not None

    manager = HTTPMagics.get_manager()
    assert manager is not None


def test_query_state_ok_mock(capsys, ip, ok_mock_api):
    status = HTTPMagics.get_manager().status(reload=True)
    ip.run_magic("query_state", "")

    captured = capsys.readouterr()
    assert f"Version: {status.version}" in captured.out, captured
    assert "Running state:" in captured.out, captured
    assert f"Manager: {status.manager_state}"
    assert "Server configuration:" in captured.out, captured
    assert f"Autostart: {status.autostart_enabled}" in captured.out, captured
    assert "Running plan information:" not in captured.out, captured


def test_query_state_running_plan_mock(capsys, ip, running_plan_mock_api):
    status = HTTPMagics.get_manager().status(reload=True)
    ip.run_magic("query_state", "")

    captured = capsys.readouterr()
    assert f"Version: {status.version}" in captured.out, captured
    assert "Running state:" in captured.out, captured
    assert f"Manager: {status.manager_state}"
    assert "Server configuration:" in captured.out, captured
    assert f"Autostart: {status.autostart_enabled}" in captured.out, captured

    assert "Running plan information:" in captured.out, captured
    assert "Plan name: setup1_load_procedure" in captured.out, captured
    assert "kwargs: 'a' = A, 'b' = 1, 'metadata' = {'aa': 'xyz', 'bb': 'fgh', 'cc': ''}" in captured.out, captured
    assert "User: fulana.beltrana" in captured.out, captured
    assert "Start time: 19:57:01 (30/01/2025)" in captured.out, captured


def test_query_history_ok_mock(capsys, ip, ok_mock_api):
    HTTPMagics.get_manager().history_get(reload=True)
    ip.run_magic("query_history", "")

    captured = capsys.readouterr()
    assert "Entry #0" in captured.out, captured
    assert "Plan name: grid_scan" in captured.out, captured
    assert "args: ['det', 'det4'], motor2, -4, 4, 15, motor1, -4, 4, 15" in captured.out, captured
    assert "kwargs: 'snake_axes' = True, 'md' = {'something': 'abc'}" in captured.out, captured
    assert "User: fulana.beltrana" in captured.out, captured
    assert "Time: 15:36:22 (23/10/2024) - 15:36:24 (23/10/2024) (Duration: 2.390s)" in captured.out, captured


def test_query_history_failed_plan_mock(capsys, ip, failed_plan_mock_api):
    HTTPMagics.get_manager().history_get(reload=True)
    ip.run_magic("query_history", "")

    captured = capsys.readouterr()
    assert "Entry #0" in captured.out, captured
    assert "Plan name: grid_scan" in captured.out, captured
    assert "args: ['det', 'det4'], motor2, -4, 4, 15, motor1, -4, 4, 15" in captured.out, captured
    assert "kwargs: 'snake_axes' = True, 'md' = {'something': 'abc'}" in captured.out, captured
    assert "User: fulana.beltrana" in captured.out, captured
    assert "Time: 15:36:22 (23/10/2024) - 15:36:24 (23/10/2024) (Duration: 2.390s)" in captured.out, captured

    assert "Plan failed: Failed to connect to <PV> within 30.00 sec" in captured.out, captured
    assert "Traceback (most recent call last):" in captured.out, captured


def test_reload_devices_ok_mock(ip, ok_mock_api):
    HTTPMagics.get_manager().devices_allowed(reload=True)
    ip.run_magic("reload_devices", "")

    devices = get_from_namespace(NamespaceKeys.DEVICES, ipython=ip)
    assert isinstance(devices, set)

    assert "a" in devices
    assert "b" in devices


def test_reload_devices_custom_renderer_ok_mock(ip, ok_mock_api):
    def custom_renderer(inp):
        return ["custom_" + x for x in inp.keys()]

    old_renderer = ip.magics_manager.registry["HTTPMagics"].device_list_renderer
    ip.magics_manager.registry["HTTPMagics"].device_list_renderer = custom_renderer

    try:
        HTTPMagics.get_manager().devices_allowed(reload=True)
        ip.run_magic("reload_devices", "")

        devices = get_from_namespace(NamespaceKeys.DEVICES, ipython=ip)
        assert isinstance(devices, list)

        assert "custom_a" in devices
        assert "custom_b" in devices
    finally:
        ip.magics_manager.registry["HTTPMagics"].device_list_renderer = old_renderer
