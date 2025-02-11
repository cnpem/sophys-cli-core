import subprocess

from sophys.cli.core.__main__ import create_kernel


def test_run_command_api(capsys):
    start_cls, kwargs = create_kernel(False, False, False, True, start_command=["""print("hi there!")"""], extension_name="skip")
    start_cls(**kwargs)

    out, _ = capsys.readouterr()

    assert "hi there!" in out


def test_run_command_subprocess_simple():
    proc = subprocess.run(["sophys-cli", "skip", "-c", "print('hi there!')"], capture_output=True)
    proc.check_returncode()

    assert "hi there!" in str(proc.stdout)


def test_run_command_subprocess_userns():
    proc = subprocess.run(["sophys-cli", "skip", "-c", "print(EXTENSION)"], capture_output=True)
    proc.check_returncode()

    assert "skip" in str(proc.stdout)
