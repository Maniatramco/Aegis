$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../../ags_local_use/ags_scripts/model-hardware.ps1"
if ((Resolve-AegisHardware -Mode Auto -Probe { $true }) -ne 'Gpu') { throw 'Accessible GPU selection failed.' }
if ((Resolve-AegisHardware -Mode Auto -Probe { $false }) -ne 'Cpu') { throw 'Unavailable GPU fallback failed.' }
if ((Resolve-AegisHardware -Mode Cpu -Probe { throw 'CPU must not probe or require GPU.' }) -ne 'Cpu') { throw 'Forced CPU failed.' }
$taskRejected = $false
try { Resolve-AegisHardware -Mode Gpu -Probe { $false } } catch { $taskRejected = $true }
if (-not $taskRejected) { throw 'Explicit unavailable GPU should fail clearly.' }
Write-Host 'Hardware selection: 4 checks passed (including CPU without a GPU probe).'
