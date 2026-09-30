# One-time setup: venv + crashlink, verify build, extract data, index bytecode.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File ai-mod\setup.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }
.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt
.\mod.cmd verify
.\mod.cmd build | Out-Null   # extracts + caches work\data.original.cdb
.\mod.cmd index
Write-Host "Ready. Next: .\ai-mod\mod.cmd testbed on   (see ai-mod\docs\TESTBED.md)"
