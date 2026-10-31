<#
.SYNOPSIS
  Plan Aegis OCI infrastructure, show exactly what will be created, and apply ONLY after
  the operator types PROVISION. Windows PowerShell 5.1+ or PowerShell 7.

.DESCRIPTION
  1. terraform init + terraform plan (saved to tfplan). Terraform prompts for the ADMIN password
     unless TF_VAR_adb_admin_password is set.
  2. Prints every resource that would be created, changed, replaced or destroyed, the key sizing
     (node shape, OCPUs, memory, database ECPU/storage/free tier, bucket, region) and a cost reminder.
  3. Waits for the operator to type PROVISION. Anything else stops without changes.
     A plan that destroys or replaces resources needs DESTROY typed first as well.
  4. terraform apply tfplan (exactly the reviewed plan, nothing re-planned).

  Approval words are never accepted from parameters or pipes; they must be typed by the operator.
  -PlanOnly stops after step 2.
#>
[CmdletBinding()]
param([switch]$PlanOnly)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Terraform([string[]]$Arguments) {
    & terraform @Arguments
    if ($LASTEXITCODE -ne 0) { throw "terraform $($Arguments -join ' ') failed with exit code $LASTEXITCODE. Nothing was provisioned by this step." }
}

function Read-Approval([string]$Word, [string]$Message) {
    if ([Console]::IsInputRedirected) { throw "Approval must be typed interactively; input is redirected. Stopping without changes." }
    Write-Host ''
    Write-Host $Message -ForegroundColor Yellow
    $answer = Read-Host "Type $Word to continue (anything else stops)"
    if ($answer -cne $Word) { Write-Host 'Not approved. No resources were created or changed.' -ForegroundColor Red; exit 1 }
}

if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) { throw 'terraform is not on PATH. Install Terraform 1.5+ (winget install Hashicorp.Terraform).' }
if (-not (Test-Path -LiteralPath .\terraform.tfvars)) {
    throw 'terraform.tfvars is missing. Copy terraform.tfvars.example to terraform.tfvars and fill tenancy_ocid, region and operator_cidr.'
}

Write-Host '== Aegis OCI provisioning: PLAN ONLY (no changes yet) ==' -ForegroundColor Cyan
Invoke-Terraform @('init', '-input=false')
Invoke-Terraform @('plan', '-out=tfplan')

$plan = (& terraform show -json tfplan) | Out-String | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Could not read the saved plan.' }

$changes = @($plan.resource_changes | Where-Object { $_.mode -eq 'managed' -and ($_.change.actions -join ',') -ne 'no-op' })
$creates  = @($changes | Where-Object { ($_.change.actions -join ',') -eq 'create' })
$updates  = @($changes | Where-Object { ($_.change.actions -join ',') -eq 'update' })
$destroys = @($changes | Where-Object { $_.change.actions -contains 'delete' })

Write-Host ''
Write-Host '== What will happen if you approve ==' -ForegroundColor Cyan
$vars = $plan.variables
Write-Host ("Region: {0}   OCI profile: {1}   Compartment: {2}" -f $vars.region.value, $vars.oci_profile.value,
    $(if ($vars.compartment_ocid.value) { $vars.compartment_ocid.value } else { 'NEW compartment "' + $vars.compartment_name.value + '"' }))
foreach ($c in $creates)  { Write-Host ('  CREATE   ' + $c.address) -ForegroundColor Green }
foreach ($c in $updates)  { Write-Host ('  UPDATE   ' + $c.address) -ForegroundColor Yellow }
foreach ($c in $destroys) { Write-Host ('  ' + ($(if ($c.change.actions -contains 'create') { 'REPLACE  ' } else { 'DESTROY  ' })) + $c.address) -ForegroundColor Red }

$pool = $changes | Where-Object { $_.type -eq 'oci_containerengine_node_pool' } | Select-Object -First 1
if ($pool) {
    $a = $pool.change.after
    Write-Host ("Kubernetes node(s): {0} x {1}, {2} OCPU, {3} GB RAM, {4} GB boot" -f $a.node_config_details[0].size, $a.node_shape,
        $a.node_shape_config[0].ocpus, $a.node_shape_config[0].memory_in_gbs, $a.node_source_details[0].boot_volume_size_in_gbs)
}
$db = $changes | Where-Object { $_.type -eq 'oci_database_autonomous_database' } | Select-Object -First 1
if ($db) {
    $a = $db.change.after
    if ($a.is_free_tier) { Write-Host ("Autonomous AI Database: {0} (Always Free)" -f $a.db_name) }
    else { Write-Host ("Autonomous AI Database: {0}, {1} ECPU, {2} GB, version {3}" -f $a.db_name, $a.compute_count, $a.data_storage_size_in_gb, $a.db_version) }
}
$bucket = $changes | Where-Object { $_.type -eq 'oci_objectstorage_bucket' } | Select-Object -First 1
if ($bucket) { Write-Host ("Bucket: {0} (private)" -f $bucket.change.after.name) }
Write-Host ("Totals: {0} to create, {1} to change, {2} to destroy/replace" -f $creates.Count, $updates.Count, $destroys.Count)
Write-Host 'Cost: OKE node, Autonomous Database (unless Always Free), block volumes and the later load balancer may be billed. Check the OCI cost estimator and your limits.' -ForegroundColor Yellow

if ($changes.Count -eq 0) { Write-Host 'Nothing to do; infrastructure already matches.'; exit 0 }
if ($PlanOnly) { Write-Host 'PlanOnly: stopped before any change. Saved plan: tfplan'; exit 0 }

if ($destroys.Count -gt 0) {
    Read-Approval 'DESTROY' ("This plan DESTROYS or REPLACES {0} existing resource(s) listed in red above." -f $destroys.Count)
}
Read-Approval 'PROVISION' 'Approve creating/changing exactly the resources listed above in this tenancy.'

Write-Host '== Applying the reviewed plan ==' -ForegroundColor Cyan
Invoke-Terraform @('apply', '-input=false', 'tfplan')
Remove-Item -LiteralPath .\tfplan -ErrorAction SilentlyContinue
Write-Host ''
Write-Host 'Provisioning finished. Next: terraform output (kubeconfig_command, wallet_command, deployment_inputs, seed_values).' -ForegroundColor Green
