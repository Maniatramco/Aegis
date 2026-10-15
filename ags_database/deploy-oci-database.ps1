#Requires -Version 5.1
<#
.SYNOPSIS
Installs the verified Aegis schema into a separate, empty OCI Oracle database owner.
.DESCRIPTION
Uses SQLcl and the destination wallet. SQLcl prompts privately for the database
password; credentials are never accepted as script arguments or written to SQL.
The shared install.sql checks the actual owner/service and refuses existing objects.
Use -CheckOnly for local package checks without starting SQLcl or connecting.
.EXAMPLE
.\ags_database\deploy-oci-database.ps1 -WalletPath C:\aegis-target\Wallet_NEWDB.zip -UserName AGS_APP -ServiceAlias NEWDB_low -ExpectedService YOUR_FULL_SERVICE_NAME.adb.oraclecloud.com -CheckOnly
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory)][string]$WalletPath,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z][A-Za-z0-9_$#]{0,127}$')][string]$UserName,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$ServiceAlias,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$ExpectedService,
    [string]$SqlclPath = 'sql',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$owner = $UserName.ToUpperInvariant()
if ($owner -in @('SYS', 'SYSTEM')) { throw 'Use the prepared destination application owner.' }
$wallet = (Resolve-Path -LiteralPath $WalletPath).Path
if (-not (Test-Path -LiteralPath $wallet -PathType Leaf) -or
    [IO.Path]::GetExtension($wallet) -ine '.zip') {
    throw 'WalletPath must identify the destination Autonomous Database wallet ZIP.'
}
if ($wallet -match '["\r\n]') { throw 'WalletPath cannot contain double quotes or line breaks.' }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($wallet)
try {
    $tnsEntries = @($archive.Entries | Where-Object { $_.Name -ieq 'tnsnames.ora' })
    if ($tnsEntries.Count -ne 1) { throw 'Wallet ZIP must contain exactly one tnsnames.ora.' }
    $reader = [IO.StreamReader]::new($tnsEntries[0].Open())
    try { $tns = $reader.ReadToEnd() } finally { $reader.Dispose() }
    if ($tns -notmatch ('(?im)^\s*' + [regex]::Escape($ServiceAlias) + '\s*=')) {
        throw 'ServiceAlias was not found in this wallet.'
    }
    if ($tns -notmatch ('(?i)SERVICE_NAME\s*=\s*' + [regex]::Escape($ExpectedService) + '\s*\)')) {
        throw 'ExpectedService was not found in this wallet. Supply the full server service, not the TNS alias.'
    }
} finally { $archive.Dispose() }

$installer = Join-Path $PSScriptRoot 'install.sql'
$includeMatches = [regex]::Matches([IO.File]::ReadAllText($installer), '(?m)^@@([^\r\n]+)')
if ($includeMatches.Count -ne 13) { throw 'The schema package must contain thirteen ordered table scripts.' }
foreach ($include in $includeMatches) {
    $relative = $include.Groups[1].Value
    if ($relative -notmatch '^ags_tables/[A-Za-z0-9_]+\.sql$' -or
        -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $relative) -PathType Leaf)) {
        throw "Missing or invalid table script: $relative"
    }
}

Write-Host "Target owner: $owner; wallet alias: $ServiceAlias; expected service: $ExpectedService"
if ($CheckOnly) {
    Write-Host 'Local package and wallet checks passed. No SQL client started and no database connection made.'
    return
}
if (-not $PSCmdlet.ShouldProcess("$owner@$ExpectedService", 'Install the Aegis schema into an empty owner')) { return }

$client = Get-Command -Name $SqlclPath -CommandType Application -ErrorAction Stop | Select-Object -First 1
$operation = 'aegis-oci-schema-' + [guid]::NewGuid().ToString('N')
$driver = Join-Path ([IO.Path]::GetTempPath()) ($operation + '.sql')
$log = Join-Path ([IO.Path]::GetTempPath()) ($operation + '.log')
if (($driver + $log) -match '["\r\n]') { throw 'The temporary directory cannot contain double quotes or line breaks.' }
$driverSql = @"
SET ECHO OFF
SET VERIFY OFF
SET DEFINE OFF
WHENEVER OSERROR EXIT FAILURE ROLLBACK
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
SET CLOUDCONFIG "$wallet"
CONNECT $owner@$ServiceAlias
SPOOL "$log"
@install.sql $owner $ExpectedService
EXIT FAILURE
"@

try {
    [IO.File]::WriteAllText($driver, $driverSql, [Text.UTF8Encoding]::new($false))
    Write-Host "SQLcl will prompt for the destination password. Installation log: $log"
    Push-Location -LiteralPath $PSScriptRoot
    try {
        & $client.Source -L /nolog ('@"' + $driver + '"')
        $clientExitCode = $LASTEXITCODE
    } finally { Pop-Location }
    if ($clientExitCode -ne 0) { throw "SQLcl failed (exit $clientExitCode). Inspect $log; committed DDL is not automatically undone." }
    if (-not (Test-Path -LiteralPath $log -PathType Leaf) -or
        [IO.File]::ReadAllText($log) -notmatch '(?m)^AEGIS_SCHEMA_INSTALL_OK:') {
        throw "The completed-schema success marker is missing. Inspect $log before any retry."
    }
    Write-Host "Aegis schema installed and verified in $owner@$ExpectedService. Log: $log"
} finally {
    if (Test-Path -LiteralPath $driver -PathType Leaf) { Remove-Item -LiteralPath $driver }
}
