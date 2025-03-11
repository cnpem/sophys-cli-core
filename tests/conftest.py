import pytest

import os
import time

from sophys.cli.core.http_utils import RM


@pytest.fixture(scope="session", autouse=True)
def set_timezone():
    # NOTE: Arbitrary TZ. Useful for my tests because it's an hour of difference from me.
    os.environ["TZ"] = "America/Noronha"
    time.tzset()


@pytest.fixture
def typed_rm(http_server_uri):
    return RM(http_server_uri=http_server_uri, http_auth_provider="ldap/token")
