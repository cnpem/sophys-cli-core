import pytest

import httpx

from ..data import *


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
