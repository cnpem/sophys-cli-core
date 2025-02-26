import pytest

import os
import time

import httpx

from sophys.cli.core.http_utils import RM, RemoteSessionHandler

from .mock_data import *


@pytest.fixture(scope="session", autouse=True)
def set_timezone():
    # NOTE: Arbitrary TZ. Useful for my tests because it's an hour of difference from me.
    os.environ["TZ"] = "America/Noronha"
    time.tzset()


@pytest.fixture(scope="session")
def http_server_uri():
    return "http://mocked_http_session.lnls.br"


@pytest.fixture
def typed_rm(http_server_uri):
    return RM(http_server_uri=http_server_uri, http_auth_provider="ldap/token")


@pytest.fixture(scope="session")
def no_auth_session_handler(http_server_uri):
    return RemoteSessionHandler(http_server_uri, disable_authentication=True)


@pytest.fixture
def ok_mock_api(respx_mock, http_server_uri, status_ok_mock_response, history_get_ok_mock_response, devices_get_ok_mock_response):
    respx_mock.clear()

    respx_mock.get(http_server_uri + "/api/status").mock(status_ok_mock_response)
    respx_mock.get(http_server_uri + "/api/history/get").mock(history_get_ok_mock_response)
    respx_mock.get(http_server_uri + "/api/devices/allowed").mock(devices_get_ok_mock_response)
    respx_mock.post(http_server_uri + "/api/auth/logout").mock(httpx.Response(200, json={}))

    return respx_mock


@pytest.fixture
def running_plan_mock_api(respx_mock, http_server_uri, status_running_plan_mock_response, queue_get_running_item_mock_response):
    respx_mock.clear()

    respx_mock.get(http_server_uri + "/api/status").mock(status_running_plan_mock_response)
    respx_mock.get(http_server_uri + "/api/queue/get").mock(queue_get_running_item_mock_response)
    respx_mock.post(http_server_uri + "/api/auth/logout").mock(httpx.Response(200, json={}))

    return respx_mock


@pytest.fixture
def failed_plan_mock_api(respx_mock, http_server_uri, status_failed_plan_mock_response, history_get_failed_plan_mock_response):
    respx_mock.clear()

    respx_mock.get(http_server_uri + "/api/status").mock(status_failed_plan_mock_response)
    respx_mock.get(http_server_uri + "/api/history/get").mock(history_get_failed_plan_mock_response)

    return respx_mock
