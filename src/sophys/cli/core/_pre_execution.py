from sophys.cli.core.base_configuration import execute_at_start

# Appease LSPs and allow some use of the application with no extension.
EXTENSION = globals().get("EXTENSION", None)
if EXTENSION is None:
    EXTENSION = "skip"


execute_at_start(EXTENSION, globals())
