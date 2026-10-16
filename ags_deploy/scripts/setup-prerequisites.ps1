# Windows prerequisite implementation. Dot-source; the entry point is Setup-Aegis.ps1.
function Get-AegisSetupFileHash {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','') }
    finally { $sha.Dispose(); $stream.Dispose() }
}
function Get-AegisApplication {
    param([string]$Name)
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    return $null
}

function ConvertTo-AegisProcessArgument {
    param([AllowEmptyString()][string]$Value)
    # Windows argv quoting: protect embedded quotes and trailing backslashes.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Invoke-AegisNative {
    param([string]$Program, [string[]]$Arguments, [switch]$Capture, [switch]$AllowFailure)
    $application = Get-Command $Program -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $savedPreference = $ErrorActionPreference
    try {
        if ($Capture) {
            $ErrorActionPreference = 'Continue'
            $global:LASTEXITCODE = 0
            $lines = @(& $Program @Arguments 2>&1)
            $code = $global:LASTEXITCODE
        }
        else {
            # Inherit console handles directly. A PowerShell output pipeline buffers
            # Python input()/private login prompts until a newline and hides them.
            $process = New-Object Diagnostics.Process
            try {
                $process.StartInfo.FileName = $application.Source
                $process.StartInfo.Arguments = (@($Arguments | ForEach-Object { ConvertTo-AegisProcessArgument $_ }) -join ' ')
                $process.StartInfo.WorkingDirectory = $ExecutionContext.SessionState.Path.CurrentFileSystemLocation.Path
                $process.StartInfo.UseShellExecute = $false
                $process.StartInfo.CreateNoWindow = $false
                $process.StartInfo.RedirectStandardInput = $false
                $process.StartInfo.RedirectStandardOutput = $false
                $process.StartInfo.RedirectStandardError = $false
                if (-not $process.Start()) { throw 'The prerequisite command could not start.' }
                $process.WaitForExit()
                $code = $process.ExitCode
                $global:LASTEXITCODE = $code
            }
            finally { $process.Dispose() }
        }
    }
    finally { $ErrorActionPreference = $savedPreference }
    if (-not $AllowFailure -and $code -ne 0) {
        if ($code -in @(3010,1641)) { throw 'Windows requires a restart. Restart and run Setup-Aegis.ps1 again.' }
        throw ('{0} failed (exit {1}). Review the output; no dependent step was started.' -f [IO.Path]::GetFileName($Program),$code)
    }
    $text = ''
    if ($Capture) { $text = ($lines | ForEach-Object { [string]$_ }) -join "`n" }
    return [pscustomobject]@{ExitCode=$code; Text=$text}
}

function Add-AegisSetupCheck {
    param($State, [string]$Name, [string]$Detail)
    $State.Checks.Add([pscustomobject]@{Name=$Name;Status='passed';Detail=$Detail})
    Write-Host ('[OK] ' + $Name + ': ' + $Detail)
}

function Install-AegisPackage {
    param([string]$Name, [string]$Package, [string]$Repository)
    $winget = Get-AegisApplication 'winget'
    if (-not $winget) { throw ('Install Microsoft App Installer (WinGet), reopen PowerShell and run Setup-Aegis.ps1 again. Missing: ' + $Name) }
    Write-Host ('Installing missing prerequisite: ' + $Name + '. Complete any installer/UAC prompts.')
    Write-Host ('Running: winget install --id ' + $Package + ' --exact --source winget')
    $null = Invoke-AegisNative $winget @('install','--id',$Package,'--exact','--source','winget')
    Initialize-AegisDeploymentEnvironment $Repository
}

function Ensure-AegisTool {
    param([string]$Name,[string]$Package,[string]$Repository,[bool]$InstallMissing)
    $application = Get-AegisApplication $Name
    if (-not $application) {
        if (-not $InstallMissing) { throw ('Missing ' + $Name + '. Run Setup-Aegis.ps1 without -CheckOnly to install it.') }
        Install-AegisPackage $Name $Package $Repository
        $application = Get-AegisApplication $Name
    }
    if (-not $application) { throw ($Name + ' is still unavailable. Reopen PowerShell, complete installation/restart and rerun setup.') }
    return $application
}

function Resolve-AegisInputPath {
    param([string]$Value,[string]$InputDirectory)
    if ($Value -eq '~' -or $Value.StartsWith('~\') -or $Value.StartsWith('~/')) {
        $Value = Join-Path $env:USERPROFILE ($Value.Substring(1).TrimStart('\','/'))
    }
    if (-not [IO.Path]::IsPathRooted($Value)) { $Value = Join-Path $InputDirectory $Value }
    return [IO.Path]::GetFullPath($Value)
}

function Get-AegisSetupSettings {
    param([string]$Inputs,[string]$DeploymentRoot,[bool]$InstallMissing,[bool]$CommittedSource=$false)
    if (-not (Test-Path -LiteralPath $Inputs -PathType Leaf)) {
        if ($InstallMissing) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $Inputs) -Force | Out-Null
            Copy-Item -LiteralPath (Join-Path $DeploymentRoot 'templates\deployment-inputs.example.json') -Destination $Inputs
        }
        throw ('Provide the filled non-secret target JSON before continuing: ' + $Inputs)
    }
    $values = Get-Content -LiteralPath $Inputs -Raw | ConvertFrom-Json
    $allowed = @('SourcePath','Ref','Kubeconfig','Context','Namespace','Registry','RegistryNamespace','Platform','AppUrl','WalletPath','DatabaseOwner','ServiceAlias','ExpectedService','BackupReference','ValidationReference','DeployFrontend','DeployBackend','DB_Object','DB_ReleaseFile','DBAdminUser','SchemaTablespace','SchemaQuotaMB')
    foreach ($property in $values.PSObject.Properties) {
        if ($allowed -cnotcontains $property.Name) { throw 'Unsupported target JSON fields. Use the current non-secret template; passwords/tokens are not allowed.' }
        if ($property.Value -isnot [string]) { throw ('JSON field must be a string: ' + $property.Name) }
    }
    foreach ($name in @('DB_Object','DeployFrontend','DeployBackend')) {
        if (-not $values.PSObject.Properties[$name] -or $values.$name.Trim().ToUpperInvariant() -notin @('Y','N')) { throw ($name + ' must be Y or N in the JSON.') }
    }
    $frontend = $values.DeployFrontend.Trim().ToUpperInvariant() -eq 'Y'
    $backend = $values.DeployBackend.Trim().ToUpperInvariant() -eq 'Y'
    $database = $values.DB_Object.Trim().ToUpperInvariant() -eq 'Y'
    if (-not ($frontend -or $backend -or $database)) { throw 'Nothing selected: DB_Object, DeployFrontend and DeployBackend cannot all be N.' }
    $root = Split-Path -Parent $DeploymentRoot
    $base = Split-Path -Parent $Inputs
    if ($values.SourcePath) { $root = Resolve-AegisInputPath $values.SourcePath $base }
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw 'SourcePath is unavailable on this computer. Correct it or leave it blank to use this checkout.' }
    $ref = 'HEAD'
    if ($CommittedSource) {
        $ref = 'ags_sprint1'
        if ($values.Ref) { $ref = $values.Ref.Trim() }
    }
    if ($ref -notmatch '^[A-Za-z0-9_][A-Za-z0-9_./-]*$') { throw 'Invalid source Ref.' }
    $kubeconfig = $null
    if ($frontend -or $backend) {
        if (-not $values.Kubeconfig) { throw 'Fill Kubeconfig in the target JSON.' }
        $kubeconfig = Resolve-AegisInputPath $values.Kubeconfig $base
        if (-not (Test-Path -LiteralPath $kubeconfig -PathType Leaf)) { throw 'Kubeconfig is unavailable on this computer. Obtain the destination-specific file and correct its JSON path.' }
        if ([string]::IsNullOrWhiteSpace([string]$values.ValidationReference)) { throw 'Fill ValidationReference with existing test/CI evidence for the selected source files. Setup does not run or invent regression results.' }
    }
    if ($database) {
        foreach ($name in @('WalletPath','DatabaseOwner','ServiceAlias','ExpectedService')) { if (-not $values.$name) { throw ('Fill ' + $name + ' for DB_Object Y.') } }
        $wallet = Resolve-AegisInputPath $values.WalletPath $base
        if (-not (Test-Path -LiteralPath $wallet -PathType Leaf)) { throw 'The selected wallet ZIP is unavailable on this computer.' }
    }
    return [pscustomobject]@{Values=$values;Source=$root;Ref=$ref;Apps=($frontend -or $backend);Database=$database;Kubeconfig=$kubeconfig}
}

function Find-AegisBootstrapPython {
    $py = Get-AegisApplication 'py'
    if ($py) {
        $probe = Invoke-AegisNative $py @('-3.12','-B','-c','import sys; print(sys.version_info >= (3, 10))') -Capture -AllowFailure
        if ($probe.ExitCode -eq 0 -and $probe.Text.Trim() -eq 'True') { return [pscustomobject]@{Program=$py;Prefix=@('-3.12')} }
    }
    $python = Get-AegisApplication 'python'
    if ($python -and $python -notmatch 'WindowsApps') {
        $probe = Invoke-AegisNative $python @('-B','-c','import sys; print(sys.version_info >= (3, 10))') -Capture -AllowFailure
        if ($probe.ExitCode -eq 0 -and $probe.Text.Trim() -eq 'True') { return [pscustomobject]@{Program=$python;Prefix=@()} }
    }
    return $null
}

function Ensure-AegisPython {
    param([string]$Repository,[bool]$InstallMissing)
    $python = Join-Path $Repository '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        if (-not $InstallMissing) { throw 'Project .venv is missing. Run Setup-Aegis.ps1 without -CheckOnly.' }
        $bootstrap = Find-AegisBootstrapPython
        if (-not $bootstrap) {
            Install-AegisPackage 'Python 3.12' 'Python.Python.3.12' $Repository
            $bootstrap = Find-AegisBootstrapPython
        }
        if (-not $bootstrap) { throw 'Supported Python is unavailable. Complete its installation and reopen PowerShell.' }
        Write-Host ('Creating project Python environment: ' + (Join-Path $Repository '.venv'))
        $null = Invoke-AegisNative $bootstrap.Program (@($bootstrap.Prefix) + @('-m','venv',(Join-Path $Repository '.venv')))
    }
    $probe = Invoke-AegisNative $python @('-B','-c','import sys; print(sys.version_info >= (3, 10))') -Capture -AllowFailure
    if ($probe.ExitCode -ne 0 -or $probe.Text.Trim() -ne 'True') { throw 'The existing project .venv is broken or older than Python 3.10. Restore a supported environment; setup will not overwrite it.' }
    return $python
}

function Ensure-AegisOracleDriver {
    param([string]$Python,[string]$Repository,[bool]$InstallMissing)
    $requirements = Join-Path $Repository 'ags_backend\requirements-oracle.txt'
    $pin = [regex]::Match([IO.File]::ReadAllText($requirements),'(?m)^oracledb==([^\r\n]+)').Groups[1].Value.Trim()
    if (-not $pin) { throw 'The maintained Oracle driver pin was not found.' }
    $probe = Invoke-AegisNative $Python @('-B','-c',"from importlib.metadata import version; print(version('oracledb'))") -Capture -AllowFailure
    if ($probe.ExitCode -ne 0 -or $probe.Text.Trim() -ne $pin) {
        if (-not $InstallMissing) { throw 'The pinned Oracle driver is missing or different. Run setup without -CheckOnly.' }
        Write-Host ('Installing pinned Oracle driver from: ' + $requirements)
        $null = Invoke-AegisNative $Python @('-m','pip','install','-r',$requirements)
        $probe = Invoke-AegisNative $Python @('-B','-c',"from importlib.metadata import version; print(version('oracledb'))") -Capture
        if ($probe.Text.Trim() -ne $pin) { throw 'The pinned Oracle driver could not be verified.' }
    }
}

function Ensure-AegisOciCli {
    param([string]$Python,[string]$Repository,[bool]$InstallMissing)
    $oci = Get-AegisApplication 'oci'
    if (-not $oci) {
        $tools = Join-Path $Repository 'ags_runtime\oci-cli'
        $oci = Join-Path $tools 'Scripts\oci.exe'
        if (-not (Test-Path -LiteralPath $oci -PathType Leaf)) {
            if (-not $InstallMissing) { throw 'Kubeconfig requires OCI CLI. Run setup without -CheckOnly to install its isolated tool environment.' }
            Write-Host ('Installing OCI CLI in isolated environment: ' + $tools)
            $null = Invoke-AegisNative $Python @('-m','venv',$tools)
            $null = Invoke-AegisNative (Join-Path $tools 'Scripts\python.exe') @('-m','pip','install','oci-cli')
        }
        Initialize-AegisDeploymentEnvironment $Repository
        if (-not (Get-AegisApplication 'oci')) { throw 'OCI CLI is still unavailable after setup.' }
    }
    $null = Invoke-AegisNative $oci @('--version') -Capture
}

function Test-AegisKubeAuthentication {
    param([string]$Kubectl,$Settings,[string]$Python,[string]$Repository,[bool]$InstallMissing)
    $local = Invoke-AegisNative $Kubectl @('--kubeconfig',$Settings.Kubeconfig,'config','view','-o','json') -Capture
    $configuration = $local.Text | ConvertFrom-Json
    $contexts = @($configuration.contexts)
    if ($Settings.Values.Context) { $contexts = @($contexts | Where-Object { $_.name -ceq $Settings.Values.Context }) }
    if ($contexts.Count -eq 0) { throw 'The selected kubeconfig/context could not be resolved locally.' }
    if ($contexts.Count -gt 1 -and -not $Settings.Values.Context) { throw 'Fill the exact Context in the target JSON because the kubeconfig contains several contexts.' }
    $userName = $contexts[0].context.user
    $selectedUser = @($configuration.users | Where-Object { $_.name -ceq $userName })
    if ($selectedUser.Count -ne 1) { throw 'The selected context has no unique authentication user.' }
    $exec = $selectedUser[0].user.exec
    if ($exec) {
        if ($exec.command -match '(^|[\\/])oci(\.exe)?$') { Ensure-AegisOciCli $Python $Repository $InstallMissing }
        elseif (-not (Get-AegisApplication $exec.command)) { throw 'The kubeconfig authentication executable is unavailable on this computer. Obtain a working destination-specific kubeconfig.' }
        foreach ($argument in @($exec.args)) {
            if ($argument -match '\.py$' -and [IO.Path]::IsPathRooted($argument) -and -not (Test-Path -LiteralPath $argument -PathType Leaf)) { throw 'A kubeconfig authentication-helper path belongs to another computer. Obtain a usable destination-specific kubeconfig.' }
        }
    }
}

function Start-AegisDockerDesktop {
    param([string]$Docker)
    $start = Invoke-AegisNative $Docker @('desktop','start','--timeout','120') -Capture -AllowFailure
    if ($start.ExitCode -eq 0) { return }
    $paths = @((Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'))
    $desktop = $paths | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if ($desktop) { Start-Process -FilePath $desktop -WindowStyle Normal | Out-Null }
}

function Ensure-AegisDocker {
    param([string]$Repository,[bool]$InstallMissing)
    $docker = Ensure-AegisTool 'docker' 'Docker.DockerDesktop' $Repository $InstallMissing
    $engine = Invoke-AegisNative $docker @('info','--format','{{.OSType}}') -Capture -AllowFailure
    if ($engine.ExitCode -ne 0 -and $InstallMissing) {
        Write-Host 'Starting Docker Desktop. Complete its first-run prompts if shown.'
        Start-AegisDockerDesktop $docker
        for ($attempt=0; $attempt -lt 30 -and $engine.ExitCode -ne 0; $attempt++) {
            Start-Sleep -Seconds 2
            $engine = Invoke-AegisNative $docker @('info','--format','{{.OSType}}') -Capture -AllowFailure
        }
        if ($engine.ExitCode -ne 0) {
            $wsl = Get-AegisApplication 'wsl'
            $wslResult = $null
            if ($wsl) { $wslResult = Invoke-AegisNative $wsl @('--version') -Capture -AllowFailure }
            if (-not $wslResult -or $wslResult.ExitCode -ne 0) {
                $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
                $admin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
                if (-not $admin -or -not $wsl) { throw 'Docker is not ready and WSL setup requires Windows administrator access. Run this setup in Administrator PowerShell and follow Docker/Windows setup prompts.' }
                $null = Invoke-AegisNative $wsl @('--install','--no-distribution')
                throw 'WSL installation was requested. Restart Windows if prompted and rerun Setup-Aegis.ps1; deployment readiness is not yet verified.'
            }
        }
    }
    if ($engine.ExitCode -ne 0) { throw 'Docker engine is unavailable. Complete Docker Desktop setup, start its engine and rerun Setup-Aegis.ps1.' }
    if ($engine.Text -notmatch '(?m)^linux\s*$') { throw 'Docker must use Linux containers. Switch Docker Desktop to Linux containers and rerun setup.' }
    return $docker
}

function Test-AegisBuilderPlatform {
    param([string]$Docker,[string]$Platform)
    $builder = Invoke-AegisNative $Docker @('buildx','inspect') -Capture
    $platforms = @()
    foreach ($match in [regex]::Matches($builder.Text,'(?m)^\s*Platforms:\s*([^\r\n]+)')) {
        $platforms += $match.Groups[1].Value -split ',' | ForEach-Object { $_.Trim().TrimEnd('*') }
    }
    if ($platforms -notcontains $Platform) { throw ('The active Docker builder does not advertise ' + $Platform + '. Prepare a matching local builder before deployment.') }
}

function Get-AegisFreeSpaceGB {
    param([string]$Repository)
    $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($Repository))
    return $drive.AvailableFreeSpace / 1GB
}

function Test-AegisRegistry {
    param([string]$Docker,$Preflight,[bool]$InstallMissing)
    $registry = [string]$Preflight.registry
    if ($registry -notmatch '^[A-Za-z0-9.-]+$') { throw 'The selected image registry could not be resolved safely.' }
    Write-Host ('Registry prerequisite: ' + $registry + '. Setup never pushes an image or tests push permission by writing.')
    if ($InstallMissing) {
        Write-Host 'Docker will reuse stored login or ask privately for your existing registry username and auth token.'
        $null = Invoke-AegisNative $Docker @('login',$registry)
    }
    $images = @()
    foreach ($component in @($Preflight.preflight.components)) {
        if ($component -eq 'frontend') { $images += $Preflight.preflight.previous_images.'aegis-web'.web }
        else { $images += $Preflight.preflight.previous_images.'aegis-api-worker'.api }
    }
    foreach ($image in $images | Select-Object -Unique) {
        $prefix = $registry + '/' + $Preflight.registry_namespace + '/'
        if (-not $image.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) {
            if (-not $InstallMissing) { throw 'Read-only mode cannot verify login for a different destination registry. Run normal setup for registry authentication.' }
            continue
        }
        $null = Invoke-AegisNative $Docker @('manifest','inspect',$image) -Capture
    }
}

function Invoke-AegisPrerequisites {
    param([Parameter(Mandatory)][string]$DeploymentRoot,[Parameter(Mandatory)][string]$Inputs,[bool]$InstallMissing=$true,[bool]$CommittedSource=$false)
    $repository = Split-Path -Parent $DeploymentRoot
    $Inputs = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Inputs)
    Initialize-AegisDeploymentEnvironment $repository
    $run = Join-Path $repository ('ags_runtime\deployment-setup\setup-' + (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
    New-Item -ItemType Directory -Path $run -Force | Out-Null
    $reportPath = Join-Path $run 'result.json'
    $state = [ordered]@{State='checking';ReportPath=$reportPath;Inputs=$Inputs;InstallMissing=$InstallMissing;Checks=(New-Object 'System.Collections.Generic.List[object]');Current='Target JSON';Error=$null;NotVerified=@('Actual application image builds','Registry push permission','Full regression/inference tests','Future rollout success')}
    Write-Host 'Aegis prerequisite setup: workstation tools + selected target preflight; no image build or release.'
    Write-Host ('Setup report: ' + $reportPath)
    try {
        $settings = Get-AegisSetupSettings $Inputs $DeploymentRoot $InstallMissing $CommittedSource
        $state.InputsSha256 = (Get-AegisSetupFileHash $Inputs)
        Add-AegisSetupCheck $state 'Target JSON' 'Selection and local handoff paths checked; credentials are not logged.'
        $state.Current = 'Git and selected source'
        $git = Ensure-AegisTool 'git' 'Git.Git' $repository $InstallMissing
        foreach ($checkout in @($repository,$settings.Source) | Select-Object -Unique) {
            $checkout = [IO.Path]::GetFullPath($checkout).TrimEnd('\')
            if ($Inputs.StartsWith($checkout + '\',[StringComparison]::OrdinalIgnoreCase)) {
                $tracked = Invoke-AegisNative $git @('-C',$checkout,'ls-files','--error-unmatch','--',$Inputs) -Capture -AllowFailure
                if ($tracked.ExitCode -eq 0) { throw 'The private target JSON is tracked by Git. Have the repository owner remove it from version control before proceeding.' }
                $ignored = Invoke-AegisNative $git @('-C',$checkout,'check-ignore','--no-index','--',$Inputs) -Capture -AllowFailure
                if ($ignored.ExitCode -ne 0) { throw 'The private target JSON must be ignored by Git or stored outside the checkout.' }
            }
        }
        $commit = Invoke-AegisNative $git @('-C',$settings.Source,'rev-parse','--verify','--end-of-options',($settings.Ref+'^{commit}')) -Capture
        if ($commit.Text.Trim() -notmatch '^[a-f0-9]{40,64}$') { throw 'The requested committed source could not be resolved.' }
        $state.SourceCommit = $commit.Text.Trim()
        $state.SourceMode = 'working-tree'
        if ($CommittedSource) { $state.SourceMode = 'committed' }
        Add-AegisSetupCheck $state 'Source mode/base commit' ($state.SourceMode + ' / ' + $state.SourceCommit)
        $state.Current = 'Python'
        $python = Ensure-AegisPython $repository $InstallMissing
        Add-AegisSetupCheck $state 'Python' 'Supported project virtual environment is available.'
        if ($settings.Database) {
            $state.Current = 'Oracle driver'
            Ensure-AegisOracleDriver $python $repository $InstallMissing
            Add-AegisSetupCheck $state 'Oracle driver' 'Maintained pinned driver verified; wallet/account checks follow after CONNECT.'
        }
        $docker = $null
        if ($settings.Apps) {
            $state.Current = 'Kubernetes client/authentication helper'
            $kubectl = Ensure-AegisTool 'kubectl' 'Kubernetes.kubectl' $repository $InstallMissing
            Test-AegisKubeAuthentication $kubectl $settings $python $repository $InstallMissing
            Add-AegisSetupCheck $state 'Kubernetes client' 'Local context and authentication executable available.'
            $state.Current = 'Docker and build space'
            $docker = Ensure-AegisDocker $repository $InstallMissing
            if ((Get-AegisFreeSpaceGB $repository) -lt 10) { throw 'At least 10 GiB free on the source/work drive is required by setup. Build/image storage may need more; free space without deleting application data, then rerun.' }
            Add-AegisSetupCheck $state 'Docker' 'Linux engine available; at least 10 GiB source/work-drive headroom.'
        }
        $state.Current = 'Read-only target preflight'
        $preflightPath = Join-Path $run 'target-preflight.json'
        $preflightArguments = @('-u','-B','-X','utf8',(Join-Path $DeploymentRoot 'scripts\setup-preflight.py'),'--inputs',$Inputs,'--output',$preflightPath)
        if (-not $CommittedSource) { $preflightArguments += '--working-tree' }
        $null = Invoke-AegisNative $python $preflightArguments
        $preflight = Get-Content -LiteralPath $preflightPath -Raw | ConvertFrom-Json
        if ($preflight.state -cne 'preflight-only' -or $preflight.preflight.database_installed -or $preflight.preflight.builds -cne 'Not run' -or $preflight.preflight.publication -cne 'Not attempted') { throw 'The target check did not confirm a preflight-only result.' }
        if ($preflight.preflight.source_mode -cne $state.SourceMode) { throw 'Source mode differs from the requested setup check. Review and rerun.' }
        if ($preflight.preflight.source_commit -cne $state.SourceCommit) { throw 'The selected source changed during setup. Review and rerun setup.' }
        $state.TargetPreflight = $preflightPath
        Add-AegisSetupCheck $state 'Target preflight' 'Selected target/schema/readiness/configuration checks completed read-only.'
        if ($settings.Apps) {
            $state.Current = 'Builder architecture'
            Test-AegisBuilderPlatform $docker $preflight.preflight.platform
            Add-AegisSetupCheck $state 'Builder architecture' $preflight.preflight.platform
            $state.Current = 'Registry authentication and image metadata'
            Test-AegisRegistry $docker $preflight $InstallMissing
            Add-AegisSetupCheck $state 'Registry' 'Registry access checked; matching current-image metadata checked where applicable; no push performed.'
        }
        if ((Get-AegisSetupFileHash $Inputs) -cne $state.InputsSha256) { throw 'The target JSON changed during setup. Review it and rerun.' }
        $state.State = 'ready'
        $state.Current = 'Completed'
        return [pscustomobject]@{ReportPath=$reportPath;State='ready'}
    }
    catch {
        $state.State = 'blocked'
        $state.Error = $_.Exception.Message
        throw
    }
    finally {
        $state.CompletedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
        Write-Host ('Saved setup result: ' + $reportPath)
    }
}
