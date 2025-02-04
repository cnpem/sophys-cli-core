import itertools
import json
import uuid
import time

import pytest

import httpx

from sophys.cli.core.http_utils import RM, RemoteSessionHandler, monitor_console


@pytest.fixture(scope="session")
def http_server_uri():
    return "http://mocked_http_session.lnls.br"


@pytest.fixture
def typed_rm(http_server_uri):
    return RM(http_server_uri=http_server_uri, http_auth_provider="ldap/token")


@pytest.fixture
def no_auth_session_handler(http_server_uri):
    return RemoteSessionHandler(http_server_uri, disable_authentication=True)


@pytest.fixture(scope="session")
def status_ok_mock_response():
    return httpx.Response(200, json={
        "msg": "RE Manager v0.1.2.post69.dev0+aaaaaaaa",
        "items_in_queue": 2,
        "items_in_history": 85,
        "running_item_uid": None,
        "manager_state": "idle",
        "queue_stop_pending": False,
        "queue_autostart_enabled": False,
        "worker_environment_exists": True,
        "worker_environment_state": "idle",
        "worker_background_tasks": 0,
        "re_state": "idle",
        "ip_kernel_state": "disabled",
        "ip_kernel_captured": True,
        "pause_pending": False,
        "run_list_uid": "62fa781d-5d20-4a1e-8bac-eaadbbf631f1",
        "plan_queue_uid": "36e8c483-b737-4ffb-be55-7111b71e3695",
        "plan_history_uid": "537384f1-ffba-4918-b498-8a7774f6ccb7",
        "devices_existing_uid": "52a2c1fd-b97e-4b79-9c83-0103ea78cbc6",
        "plans_existing_uid": "f957099f-1a1a-4276-836c-654dfdec60b8",
        "devices_allowed_uid": "3d22e7fc-6c38-4afd-9fcd-4143e28e6ea6",
        "plans_allowed_uid": "269b06cb-762d-4337-a8f6-bc0fd0bca7cf",
        "plan_queue_mode": {
            "loop": False,
            "ignore_failures": False
        },
        "task_results_uid": "1728265d-0f7e-4101-8b8c-6da37cd46844",
        "lock_info_uid": "911e3a68-7d14-455c-aab0-af91e6451f3e",
        "lock": {
            "environment": False,
            "queue": False
        }
    })


@pytest.fixture
def mock_api(respx_mock, http_server_uri, status_ok_mock_response):
    respx_mock.get(http_server_uri + "/api/status").mock(status_ok_mock_response)
    respx_mock.post(http_server_uri + "/api/auth/logout").mock(httpx.Response(200, json={}))

    return respx_mock


def test_typed_rm_status(typed_rm, mock_api, status_ok_mock_response):
    returned_status = typed_rm.status()
    mocked_json = status_ok_mock_response.json()

    assert returned_status.version == mocked_json["msg"]
    assert returned_status.num_items_in_queue == mocked_json["items_in_queue"]
    assert returned_status.num_items_in_history == mocked_json["items_in_history"]
    assert returned_status.manager_state == mocked_json["manager_state"]

    assert returned_status.uids.run_list == mocked_json["run_list_uid"]
    assert returned_status.uids.plan_queue == mocked_json["plan_queue_uid"]

    assert returned_status.queue_mode.loop == mocked_json["plan_queue_mode"]["loop"]


def test_remote_session_handler_no_auth_get_manager(no_auth_session_handler):
    rm = no_auth_session_handler.get_authorized_manager()

    assert isinstance(rm, RM), f"The RunEngineManager instance returned by the session handler has type {str(type(rm))}."


def test_remote_session_handler_no_auth_run(no_auth_session_handler):
    no_auth_session_handler.start()

    assert no_auth_session_handler.is_alive()

    no_auth_session_handler.close()
    no_auth_session_handler.join(2.0)
    assert not no_auth_session_handler.is_alive()

    rm = no_auth_session_handler.get_authorized_manager()
    assert rm._is_closing  # Which also means it is already closed.


@pytest.fixture
def console_monitor_mock_api(http_server_uri, mock_api):
    console_lines: list[tuple[str, str]] = [(0, "first message")]

    def console_output_update(request: httpx.Request):
        start_uid = json.loads(request.content)["last_msg_uid"]

        uid = console_lines[-1][0]

        filtered_output_it = itertools.dropwhile(lambda line: line[0] != start_uid, console_lines)
        console_output = list({"msg": i[1]} for i in filtered_output_it)[1:]

        return httpx.Response(200, json={"last_msg_uid": uid, "console_output_msgs": console_output})

    mock_api.get(http_server_uri + "/api/console_output").mock(
        httpx.Response(200, json={
            "success": True, "msg": "", "text": "\n".join(i[1] for i in console_lines)
        })
    )

    mock_api.get(http_server_uri + "/api/console_output/uid").mock(
        httpx.Response(200, json={
            "success": True,
            "msg": "",
            "console_output_uid": str(uuid.UUID(int=len(console_lines)))
        })
    )

    mock_api.get(http_server_uri + "/api/console_output_update").mock(
        side_effect=console_output_update
    )

    return {"api": mock_api, "console": console_lines}


def test_monitor_console(console_monitor_mock_api, typed_rm):
    console_monitor = typed_rm.console_monitor

    last_line_received_time = time.monotonic()

    sent_message_id = 1
    received_message_id = 0

    def on_line_received(line):
        nonlocal received_message_id
        received_message_id += 1

        assert line == console_monitor_mock_api["console"][received_message_id][1]

        nonlocal last_line_received_time
        last_line_received_time = time.monotonic()

    with monitor_console(console_monitor, on_line_received=on_line_received):
        for _ in range(5):
            console_monitor_mock_api["console"].append((sent_message_id, f"This is line {sent_message_id}!"))
            sent_message_id += 1

        while received_message_id < 5 and time.monotonic() - last_line_received_time < 2.0:
            time.sleep(0.01)

        for _ in range(5):
            console_monitor_mock_api["console"].append((sent_message_id, f"This is line {sent_message_id}!"))
            sent_message_id += 1

        while received_message_id < 10 and time.monotonic() - last_line_received_time < 2.0:
            time.sleep(0.01)

    assert received_message_id == 10, "Console monitor callback was not called enough times!"
