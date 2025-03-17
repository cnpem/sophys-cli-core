import logging

BANNER_NAME_EXTEND = 20  # This many space between the name and the ':'.

AUTOSAVE_HOST_ENVVAR = "CLI_AUTOSAVE_HOST_ADDRESS"
AUTOSAVE_PORT_ENVVAR = "CLI_AUTOSAVE_PORT_ADDRESS"
REDIS_HOST_ENVVAR = "CLI_REDIS_HOST_ADDRESS"
REDIS_PORT_ENVVAR = "CLI_REDIS_PORT_ADDRESS"
HTTPSERVER_HOST_ENVVAR = "CLI_HTTPSERVER_HOST_ADDRESS"
HTTPSERVER_PORT_ENVVAR = "CLI_HTTPSERVER_PORT_ADDRESS"
KAFKA_HOST_ENVVAR = "CLI_KAFKA_HOST_ADDRESS"
KAFKA_PORT_ENVVAR = "CLI_KAFKA_PORT_ADDRESS"
KAFKA_TOPIC_ENVVAR = "CLI_KAFKA_TOPIC_NAME"

CLI_AUTOSAVE_HOST_ADDRESS_DEF = "localhost"
CLI_AUTOSAVE_PORT_ADDRESS_DEF = "1"
CLI_REDIS_HOST_ADDRESS_DEF = "localhost"
CLI_REDIS_PORT_ADDRESS_DEF = "6379"
CLI_HTTPSERVER_HOST_ADDRESS_DEF = "localhost"
CLI_HTTPSERVER_PORT_ADDRESS_DEF = "1"
CLI_KAFKA_HOST_ADDRESS_DEF = "localhost"
CLI_KAFKA_PORT_ADDRESS_DEF = "9092"
CLI_KAFKA_TOPIC_NAME_DEF = "test_bluesky_raw_docs"


def get_cli_envvar(envvar_name: str) -> str:
    import os

    var = os.environ.get(envvar_name, None)
    if var is not None:
        return var

    logging.warning(f"The environment variable '{envvar_name}' is not set. Using a default value.")
    return globals().get(envvar_name + "_DEF", "NO_DEFAULT")


class EnvironmentVariables:
    # NOTE: These are for autocomplete purposes.
    AUTOSAVE_HOST = None
    AUTOSAVE_PORT = None
    REDIS_HOST = None
    REDIS_PORT = None
    HTTPSERVER_HOST = None
    HTTPSERVER_PORT = None
    KAFKA_HOST = None
    KAFKA_PORT = None
    KAFKA_TOPIC = None

    def __getattribute__(self, name):
        var_name = name + "_ENVVAR"
        return get_cli_envvar(globals().get(var_name, var_name))


ENVVARS = EnvironmentVariables()
