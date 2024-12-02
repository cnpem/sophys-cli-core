BANNER_NAME_EXTEND = 20  # This many space between the name and the ':'.

REDIS_HOST_ENVVAR = "CLI_REDIS_HOST_ADDRESS"
REDIS_PORT_ENVVAR = "CLI_REDIS_PORT_ADDRESS"
HTTPSERVER_HOST_ENVVAR = "CLI_HTTPSERVER_HOST_ADDRESS"
HTTPSERVER_PORT_ENVVAR = "CLI_HTTPSERVER_PORT_ADDRESS"

CLI_REDIS_HOST_ADDRESS_DEF = "localhost"
CLI_REDIS_PORT_ADDRESS_DEF = "6379"
CLI_HTTPSERVER_HOST_ADDRESS_DEF = "localhost"
CLI_HTTPSERVER_PORT_ADDRESS_DEF = "1"


def get_cli_envvar(envvar_name: str) -> str:
    import os
    return os.environ.get(envvar_name, globals().get(envvar_name + "_DEF", "NO_DEFAULT"))
