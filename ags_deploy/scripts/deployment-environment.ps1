# Session-only tool discovery; no persistent PATH or account changes.
function Initialize-AegisDeploymentEnvironment {
    param([Parameter(Mandatory)][string]$Repository)
    if ($env:OS -ne 'Windows_NT') { return }
    $paths = @(
        (Join-Path $Repository 'ags_runtime\oci-cli\Scripts'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links'),
        (Join-Path $env:ProgramFiles 'Git\cmd'),
        (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'),
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin')
    )
    $paths += $env:Path -split ';'
    foreach ($scope in @('Machine','User')) {
        $configured = [Environment]::GetEnvironmentVariable('Path', $scope)
        if ($configured) { $paths += [Environment]::ExpandEnvironmentVariables($configured) -split ';' }
    }
    $unique = New-Object 'System.Collections.Generic.List[string]'
    foreach ($path in $paths) {
        if ($path -and -not ($unique -contains $path)) { $unique.Add($path) }
    }
    $env:Path = $unique -join ';'
}
