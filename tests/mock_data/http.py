import pytest

import copy

import httpx


@pytest.fixture(scope="session")
def status_ok_base():
    return {
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
    }


@pytest.fixture(scope="session")
def status_ok_mock_response(status_ok_base):
    return httpx.Response(200, json=status_ok_base)


@pytest.fixture(scope="session")
def status_running_plan_mock_response(status_ok_base):
    response = copy.deepcopy(status_ok_base)
    response["running_item_uid"] = "1720dc81-3217-476f-8519-f35d7112bda4"

    return httpx.Response(200, json=response)


@pytest.fixture(scope="session")
def queue_get_running_item_mock_response():
    return httpx.Response(200, json={
        "success": True,
        "msg": "",
        "plan_queue_uid": "36e8c483-b737-4ffb-be55-7111b71e3695",
        "running_item": {
            "name": "setup1_load_procedure",
            "args": [],
            "kwargs": {
                "a": "A",
                "b": "1",
                "metadata": {
                    "aa": "xyz",
                    "bb": "fgh",
                    "cc": ""
                }
            },
            "item_type": "plan",
            "user": "fulana.beltrana",
            "user_group": "primary",
            "item_uid": "1720dc81-3217-476f-8519-f35d7112bda4",
            "properties": {
                "time_start": 1738274221.7140498,
                "time_stop": 1738293258.9105783,
            },
        },
        "items": [],
    })


