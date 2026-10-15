#Requires -Version 5.1

<#
.SYNOPSIS
One command for an Aegis database/schema and frontend/API/worker code release.
.DESCRIPTION
Without arguments, prompts for missing non-secret inputs. -Inputs accepts a JSON
file based on deployment-inputs.example.json. Requires prepared OCI resources,
existing authentication and Python 3.10+. DB_Object, DeployFrontend and DeployBackend
use Y/N. DB_ReleaseFile selects the ordered database release JSON. DB_Object=Y needs
python-oracledb, a wallet and existing database access. The release file can permit
a missing application user/schema, with private passwords; matching objects are
preserved. Database-only releases need no Docker or Kubernetes. Application releases
need Docker and kubectl. Creates no OCI database instance, OKE resources or Secrets.
Existing configuration and users/grants are preserved. Prompts CONNECT
before remote inspection and PUBLISH before DDL/image publication. Passwords stay
in private SQLcl prompts. -CheckOnly makes no database or deployment changes.
.EXAMPLE
.\ags_deploy\deploy.ps1
.EXAMPLE
.\ags_deploy\deploy.ps1 -Inputs C:\aegis-target\target.json
.EXAMPLE
.\ags_deploy\deploy.ps1 -Inputs C:\aegis-target\target.json -CheckOnly
Credits: uses the existing Aegis database and application release helpers.
#>
[CmdletBinding()]
param([string]$Inputs, [switch]$CheckOnly, [string]$Python)
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $localPython = Join-Path $repository '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython -PathType Leaf) { $Python = $localPython }
    else { $Python = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source }
}
$cliArguments = @('-B', '-X', 'utf8', (Join-Path $PSScriptRoot 'release_cli.py'))
if ($Inputs) { $cliArguments += @('--inputs', $Inputs) }
if ($CheckOnly) { $cliArguments += '--check-only' }
& $Python @cliArguments
if ($LASTEXITCODE -ne 0) { throw "Aegis deployment stopped (exit $LASTEXITCODE). Read the phase/result above; no automatic retry or rollback was attempted." }
