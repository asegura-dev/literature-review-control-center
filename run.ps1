<#
.SYNOPSIS
    uv wrapper that keeps the virtual environment out of this folder.

.DESCRIPTION
    The environment lives in $env:USERPROFILE\.venvs\lrcc rather than in a .venv
    here, because a checkout can sit inside a synchronised folder (OneDrive,
    Dropbox, iCloud). A synchroniser that reaches the environment locks files
    mid-build, so `uv sync` fails with "Access is denied" and leaves a
    half-removed directory behind. A directory junction is not enough:
    synchronisers traverse reparse points. With UV_PROJECT_ENVIRONMENT nothing
    belonging to the environment exists inside this folder at all (ADR-0002).

    scripts/uv_run.py does the same for pre-commit hooks, which do not pass
    through this file. tests/test_environment.py checks that both name the same
    environment.

.EXAMPLE
    .\run.ps1 sync
    .\run.ps1 run pytest
    .\run.ps1 run ruff check .
#>

# A VIRTUAL_ENV inherited from an activated shell would be reported as a mismatch on
# every command. The environment below is the one this project uses.
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
$env:UV_PROJECT_ENVIRONMENT = Join-Path $env:USERPROFILE ".venvs\lrcc"
& uv @args
exit $LASTEXITCODE
