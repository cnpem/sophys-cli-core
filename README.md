# sophys-cli-core

A command-line client for the sophys project group.

This is the core project of the client, providing basic and common functionality for all extensions.

## Installation

To use it, you'll have to be in a valid Python environment (consider using [micromamba](https://mamba.readthedocs.io/en/latest/user_guide/micromamba.html)). In there, you'll need to do the following:

Normal installation (TODO: Create pre-built packages):

```bash
$ pip install git+https://github.com/cnpem/sophys-cli-core.git
```

Developer installation:

```bash
$ cd <path where you will clone the sophys-cli package>
$ git clone https://github.com/cnpem/sophys-cli-core.git
$ pip install -e sophys-cli-core
```

With that, you'll have access to the `sophys-cli` command in the environment you installed it. Furthermore, to use `sophys-cli` with a particular beamline configuration, you must also install the `sophys-<beamline>` package in that environment. After that, to use that configuration, see the [Usage](#usage) section.

## Usage

With the package installed, you can launch it via a terminal configured in the proper environment, like so:

```bash
$ sophys-cli <arguments>
```

The allowed arguments are printed with the `-h/--help` flags, like so:

```bash
$ sophys-cli -h
usage: sophys-cli [-h] [--debug] [--local] [--test] [--nocolor] extension

positional arguments:
  extension    The extension to load the configuration from.

options:
  -h, --help  show this help message and exit
  --debug     Configure debug mode, with more verbose logging and error messgaes.
  --local     Use a local RunEngine instead of communicating with HTTPServer.
  --test      Setup testing configurations to test the tool without interfering with production configured parameters.
  --nocolor   Remove color codes from rich output.
```

### Running commands and scripts automatically

When using pure IPython, we have arguments like `-c`, `-m` and `-i` that allow us to run pre-created routines and code, enabling some form of higher-level automation. In `sophys-cli`, we currently support the `-c` and `-i` flags, working in the same way they would do in IPython (it's actually [exactly passing it on for IPython to deal with it](https://github.com/cnpem/sophys-cli-core/blob/main/src/sophys/cli/core/__main__.py#L122)!).

You can use `-c` directly to run a single line of prompt, or you can use the [`%run`](https://ipython.readthedocs.io/en/stable/interactive/magics.html#magic-run) magic to run an entire script.

As an example of that second case, we could have a file called `my_routine.ipy` in `/home/cool_user/`, with the following:

```python
print("Starting linear scans...")

for i in range(10, 100, 10):
  %scan -d SIM_det -m SIM_motor -2 2 --num $i

print("Performing grid scan...")

%grid_scan -d SIM_det4 -m SIM_motor1 -2 2 10 SIM_motor2 -2 2 10

print("Scans completed successfully. Have a nice day!")
```

Then, running that whole procedure non-interactively is a matter of calling:

```bash
sophys-cli <extension> -c "%run /home/cool_user/my_routine.ipy"
```

## Development

### Creating your own extension

To create your own extension and make it acessible via the application, it is necessary that the created package have an IPython entrypoint (a function called [`load_ipython_extension`](https://ipython.readthedocs.io/en/stable/config/extensions/index.html#writing-extensions)) in the python import prefix `sophys.cli.extensions.<extension name>`. This is to ensure backwards-compatibility with the monorepo era.

After doing so, and having the package installed in your environment, running `sophys-cli <extension name> [args]` ought to work as intended.

Inside that entrypoint, you can do whatever you want, but generally you'll want to configure variables in the user namespace for usage during the program lifetime, and set up magics for user convenience.

### Communicating with httpserver

One of the main features of this package in the option of transparently communicating with httpserver instead of using a local RunEngine. To do so, we can use the `RemoteSessionHandler` class from the [`http_utils`](./src/sophys/cli/http_utils.py) module, with automatically handles authentication and session management for us.

Using it should be as simple as importing `setup_remote_session_handler` from the [`sophys.cli.core.magics`](./src/sophys/cli/core/magics/__init__.py) module, and calling it on your extension entrypoint with the ipython object and httpserver address as arguments.

Besides the session management bits, we also have many pre-assembled magics for interacting with the remote server. These are located in the [`sophys.cli.extensions.tools_magics`](./src/sophys/cli/core/magics/tools_magics.py) module, under the `HTTPMagics` class.

To use that, we must register the class magics, like one would normally do in IPython (`ipython.register_magics(HTTPMagics)`), and we **can** also configure a class property, pertaining to the `reload_plans` specifically, which can use a plan whitelist object to filter out plans available on the server, based on the extension configuration, like so:

```python
from sophys.cli.core.magics.plan_magics import PlanInformation, PlanWhitelist
from sophys.cli.core.magics.plan_magics import PlanMV, PlanReadMany, PlanCount

whitelisted_plan_list = [
    PlanInformation("mov", "mov", PlanMV, has_detectors=False),
    PlanInformation("read_many", "read", PlanReadMany, has_detectors=False),
    PlanInformation("count", "count", PlanCount),
    ...
]

plan_whitelist = PlanWhitelist(*whitelisted_plan_list)

ipython.register_magics(HTTPMagics)
ipython.magics_manager.registry["HTTPMagics"].plan_whitelist = plan_whitelist
```
