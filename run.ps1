$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw "Python 3.11+ was not found. Install Python and run this script again."
    }
}

$python = ".venv\Scripts\python.exe"
& $python -m pip install -q -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

& $python -m app.cli init
& $python -m app.cli serve --host 127.0.0.1 --port 8000
