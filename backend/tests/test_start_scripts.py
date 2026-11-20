import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "start-unix.sh"


def _copy_launcher(tmp_path: Path) -> tuple[Path, Path]:
    backend = tmp_path / "backend"
    backend.mkdir()
    script = backend / "start-unix.sh"
    shutil.copyfile(SCRIPT, script)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    return script, binaries


def _run(script: Path, binaries: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(script), "--ip", "192.0.2.8"],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PATH": f"{binaries}:/usr/bin:/bin"},
    )


def test_unix_launcher_selects_supported_python_and_uses_created_venv(tmp_path):
    script, binaries = _copy_launcher(tmp_path)
    unsupported = binaries / "python3.13"
    unsupported.write_text("#!/bin/sh\nexit 1\n")
    unsupported.chmod(0o755)
    supported = binaries / "python3.12"
    supported.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = '-c' ]; then exit 0; fi\n"
        "if [ \"$1\" = '-m' ] && [ \"$2\" = 'venv' ]; then\n"
        "  mkdir -p .venv/bin\n"
        '  cp "$0" .venv/bin/python\n'
        "  exit 0\n"
        "fi\n"
        "printf '%s\\n' \"$*\" >> launcher-commands.txt\n"
    )
    supported.chmod(0o755)

    result = _run(script, binaries)

    assert result.returncode == 0, result.stderr + result.stdout
    assert (script.parent / "launcher-commands.txt").read_text().splitlines() == [
        "-m pip install -r requirements-runtime.lock.txt",
        "launcher.py --ip 192.0.2.8",
    ]


def test_unix_launcher_rejects_incompatible_existing_venv_before_install(tmp_path):
    script, binaries = _copy_launcher(tmp_path)
    supported = binaries / "python3.12"
    supported.write_text("#!/bin/sh\nexit 0\n")
    supported.chmod(0o755)
    venv_python = script.parent / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\nexit 1\n")
    venv_python.chmod(0o755)

    result = _run(script, binaries)

    assert result.returncode == 1
    assert "kopie zapasowa" in result.stdout
    assert not (script.parent / "launcher-commands.txt").exists()
