[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourcePath,
    [Parameter(Mandatory)][string]$Kubeconfig,
    [Parameter(Mandatory)][string]$Context,
    [Parameter(Mandatory)][ValidatePattern('^[a-zA-Z0-9.-]+$')][string]$Registry,
    [Parameter(Mandatory)][ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$RegistryNamespace,
    [ValidatePattern('^[a-z0-9-]+$')][string]$Namespace = 'aegis-oci',
    [ValidateSet('linux/arm64','linux/amd64')][string]$Platform = 'linux/arm64',
    [ValidateSet('All','Frontend','Backend')][string]$Components = 'All',
    [ValidatePattern('^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$')]
    [string]$Release = ('release-' + (Get-Date -Format 'yyyyMMdd-HHmmss')),
    [switch]$SkipBuild
)

# AEGIS_COMPONENT_SELECTION_V1: selected images only; omitted images stay unchanged.
# Updates an already initialized Aegis installation. This does not provision
# OCI infrastructure, initialize a fresh database, or install Kubernetes Secrets.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE). Deployment stopped." }
}

foreach ($program in @('docker', 'kubectl')) {
    Get-Command $program -ErrorAction Stop | Out-Null
}
$source = (Resolve-Path -LiteralPath $SourcePath).Path
$config = (Resolve-Path -LiteralPath $Kubeconfig).Path
foreach ($component in @('ags_frontend', 'ags_backend')) {
    if (-not (Test-Path -LiteralPath (Join-Path $source "$component/Dockerfile"))) {
        throw "Missing $component/Dockerfile in SourcePath."
    }
}
$kubectlArguments = @('--kubeconfig', $config, '--context', $Context, '-n', $Namespace)

# Confirm the requested destination exists before spending time building images.
$destinationJson = & kubectl --kubeconfig $config --context $Context config view --minify -o json
if ($LASTEXITCODE -ne 0) { throw 'Cannot read the selected Kubernetes context.' }
$destination = ($destinationJson -join "`n") | ConvertFrom-Json
if (-not $destination.clusters -or -not $destination.contexts -or $destination.contexts[0].name -ne $Context) {
    throw 'The selected Kubernetes context was not resolved.'
}
Write-Host "Destination: $Context ($($destination.clusters[0].cluster.server))"
Write-Host "Namespace: $Namespace; registry: $Registry/$RegistryNamespace; release: $Release"
Write-Host 'Registry login and destination image-pull credentials must already be configured.'

$beforeJson = & kubectl @kubectlArguments get deployment aegis-web aegis-api-worker -o json
if ($LASTEXITCODE -ne 0) { throw 'Both Aegis deployments must already exist in the destination.' }
$before = ($beforeJson -join "`n") | ConvertFrom-Json
foreach ($expected in @(
    @{ Name = 'aegis-web'; Containers = @('web') },
    @{ Name = 'aegis-api-worker'; Containers = @('api', 'worker') }
)) {
    $deployment = @($before.items | Where-Object { $_.metadata.name -eq $expected.Name })
    if ($deployment.Count -ne 1) { throw "Missing deployment $($expected.Name)." }
    foreach ($container in $expected.Containers) {
        if ($container -notin @($deployment[0].spec.template.spec.containers.name)) {
            throw "Missing container $container in $($expected.Name)."
        }
    }
}

$webImage = "$Registry/$RegistryNamespace/ags-aegis-web`:$Release"
$backendImage = "$Registry/$RegistryNamespace/ags-aegis-backend`:$Release"
$deployFrontend = $Components -in @('All', 'Frontend')
$deployBackend = $Components -in @('All', 'Backend')
$selectedImages = @()
$selectedComponents = @()
if ($deployFrontend) { $selectedImages += $webImage; $selectedComponents += 'frontend' }
if ($deployBackend) { $selectedImages += $backendImage; $selectedComponents += 'backend' }
Write-Host "Selected application components: $Components"
if (-not $SkipBuild) {
    if ($deployFrontend) {
        Invoke-Checked -Program docker -Arguments @('build', '--platform', $Platform,
            '-t', $webImage, (Join-Path $source 'ags_frontend'))
    }
    if ($deployBackend) {
        Invoke-Checked -Program docker -Arguments @('build', '--platform', $Platform,
            '--build-arg', 'INSTALL_LOCAL_EMBEDDINGS=false',
            '--build-arg', 'INSTALL_CLOUD_MODELS=false',
            '--build-arg', 'INSTALL_ORACLE=true', '--build-arg', 'INSTALL_OCI=true',
            '-t', $backendImage, (Join-Path $source 'ags_backend'))
    }
}

# With -SkipBuild, these exact destination tags must already exist locally.
foreach ($image in $selectedImages) {
    $actualPlatform = & docker image inspect $image --format '{{.Os}}/{{.Architecture}}'
    if ($LASTEXITCODE -ne 0) { throw "Local image missing: $image" }
    if (($actualPlatform -join '').Trim() -ne $Platform) {
        throw "Wrong platform for $image; expected $Platform."
    }
}

# Publish all selected images before updating any deployment.
$digests = @{}
foreach ($image in $selectedImages) {
    Invoke-Checked -Program docker -Arguments @('push', $image)
    $digestJson = & docker image inspect $image --format '{{json .RepoDigests}}'
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect published digest for $image" }
    $repository = $image.Substring(0, $image.LastIndexOf(':'))
    $taskDigestMatches = @( (($digestJson -join "`n") | ConvertFrom-Json) |
        Where-Object { $_.StartsWith($repository + '@sha256:') })
    if ($taskDigestMatches.Count -ne 1) { throw "Cannot resolve a unique digest for $image" }
    $digests[$image] = $taskDigestMatches[0]
}

$receiptDirectory = Join-Path $PSScriptRoot 'deployment-records'
New-Item -ItemType Directory -Path $receiptDirectory -Force | Out-Null
$receipt = Join-Path $receiptDirectory "$Release-$([guid]::NewGuid().ToString('N').Substring(0,8)).json"
@{
    context = $Context; server = $destination.clusters[0].cluster.server
    namespace = $Namespace; release = $Release
    components = $selectedComponents
    previous = @($before.items | ForEach-Object {
        @{ deployment = $_.metadata.name; containers = @($_.spec.template.spec.containers |
            ForEach-Object { @{ name = $_.name; image = $_.image } }) }
    })
    web_image = $(if ($deployFrontend) { $digests[$webImage] } else { $null })
    backend_image = $(if ($deployBackend) { $digests[$backendImage] } else { $null })
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $receipt -Encoding utf8
Write-Host "Previous images and destination saved: $receipt"

if ($deployBackend) {
    Invoke-Checked -Program kubectl -Arguments ($kubectlArguments + @('set', 'image',
        'deployment/aegis-api-worker', "api=$($digests[$backendImage])", "worker=$($digests[$backendImage])"))
    Invoke-Checked -Program kubectl -Arguments ($kubectlArguments + @('rollout', 'status',
        'deployment/aegis-api-worker', '--timeout=15m'))
}
if ($deployFrontend) {
    Invoke-Checked -Program kubectl -Arguments ($kubectlArguments + @('set', 'image',
        'deployment/aegis-web', "web=$($digests[$webImage])"))
    Invoke-Checked -Program kubectl -Arguments ($kubectlArguments + @('rollout', 'status',
        'deployment/aegis-web', '--timeout=15m'))
}
Write-Host 'Image rollouts completed. Run one application check: login, upload, extraction and cited chat.'
Write-Host 'If a rollout fails, inspect the saved record and the deployment before retrying. No automatic rollback is performed.'
