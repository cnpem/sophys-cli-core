import logging

from types import SimpleNamespace

BANNER_NAME_EXTEND = 20  # This many space between the name and the ':'.

AUTOSAVE_HOST_ENVVAR = "CLI_AUTOSAVE_HOST_ADDRESS"
AUTOSAVE_PORT_ENVVAR = "CLI_AUTOSAVE_PORT_ADDRESS"
REDIS_HOST_ENVVAR = "CLI_REDIS_HOST_ADDRESS"
REDIS_PORT_ENVVAR = "CLI_REDIS_PORT_ADDRESS"
HTTPSERVER_HOST_ENVVAR = "CLI_HTTPSERVER_HOST_ADDRESS"
HTTPSERVER_PORT_ENVVAR = "CLI_HTTPSERVER_PORT_ADDRESS"
KAFKA_HOST_ENVVAR = "CLI_KAFKA_HOST_ADDRESS"
KAFKA_PORT_ENVVAR = "CLI_KAFKA_PORT_ADDRESS"

CLI_AUTOSAVE_HOST_ADDRESS_DEF = "localhost"
CLI_AUTOSAVE_PORT_ADDRESS_DEF = "1"
CLI_REDIS_HOST_ADDRESS_DEF = "localhost"
CLI_REDIS_PORT_ADDRESS_DEF = "6379"
CLI_HTTPSERVER_HOST_ADDRESS_DEF = "localhost"
CLI_HTTPSERVER_PORT_ADDRESS_DEF = "1"
CLI_KAFKA_HOST_ADDRESS_DEF = "localhost"
CLI_KAFKA_PORT_ADDRESS_DEF = "9092"


def get_cli_envvar(envvar_name: str) -> str:
    import os

    var = os.environ.get(envvar_name, None)
    if var is not None:
        return var

    logging.warning(f"The environment variable '{envvar_name}' is not set. Using a default value.")
    return globals().get(envvar_name + "_DEF", "NO_DEFAULT")


ENVVARS = SimpleNamespace()
ENVVARS.AUTOSAVE_HOST_ENVVAR = AUTOSAVE_HOST_ENVVAR
ENVVARS.AUTOSAVE_PORT_ENVVAR = AUTOSAVE_PORT_ENVVAR
ENVVARS.REDIS_HOST_ENVVAR = REDIS_HOST_ENVVAR
ENVVARS.REDIS_PORT_ENVVAR = REDIS_PORT_ENVVAR
ENVVARS.HTTPSERVER_HOST_ENVVAR = HTTPSERVER_HOST_ENVVAR
ENVVARS.HTTPSERVER_PORT_ENVVAR = HTTPSERVER_PORT_ENVVAR
ENVVARS.KAFKA_HOST_ENVVAR = KAFKA_HOST_ENVVAR
ENVVARS.KAFKA_PORT_ENVVAR = KAFKA_PORT_ENVVAR
