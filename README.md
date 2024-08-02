# sophys-cli

A command-line client for the sophys project group.

## Installation

To use it, you'll have to be in a valid Python environment (consider using [micromamba](https://mamba.readthedocs.io/en/latest/user_guide/micromamba.html)). In there, you'll need to do the following:

Normal installation (TODO: Create pre-built packages):

```bash
$ pip install git+https://gitlab.cnpem.br/SOL/bluesky/sophys-cli.git
```

Developer installation:

```bash
$ cd <path where you will clone the sophys-cli package>
$ git clone https://gitlab.cnpem.br/SOL/bluesky/sophys-cli.git
$ pip install -e sophys-cli
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
usage: sophys-cli [-h] beamline

positional arguments:
  beamline    The beamline to load the configuration from.

options:
  -h, --help  show this help message and exit
```
