<#
.SYNOPSIS
Mirrors the eight shared Fabric notebooks from `3. Fabric/notebooks/`
into every self-contained location under `3. Fabric/archive/extended/`.

.DESCRIPTION
The source of truth for the shared notebooks is `3. Fabric/notebooks/`. To keep
the archived add-on copies consistent with the core, we duplicate those
notebooks into:

  3. Fabric/archive/extended/_shared/notebooks/
  3. Fabric/archive/extended/Fabric + Copilot Studio/notebooks/_core/

Run this after editing any file in `3. Fabric/notebooks/`.

`Copilot_Audit_Log_Processor.ipynb` is deliberately NOT mirrored: it is a
downstream transform (parsed -> curated), not an ingester, and the add-ons
inherit it from the base `3. Fabric` build. It is listed in $excluded below.

.PARAMETER Check
When set, exits 1 if any destination differs from the source. Used by CI.

.EXAMPLE
.\scripts\sync-shared.ps1              # sync (writes)
.\scripts\sync-shared.ps1 -Check       # verify only (CI)
#>
[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$source   = Join-Path $repoRoot '3. Fabric\notebooks'

$destinations = @(
    (Join-Path $repoRoot '3. Fabric\archive\extended\_shared\notebooks'),
    (Join-Path $repoRoot '3. Fabric\archive\extended\Fabric + Copilot Studio\notebooks\_core')
)

# Notebooks in $source that are NOT mirrored into the add-ons. The processor is
# a downstream transform, not an ingester, so the add-ons inherit it from the
# base 3. Fabric build rather than shipping their own copy.
$excluded = @(
    'Copilot_Audit_Log_Processor.ipynb'
)

$notebooks = Get-ChildItem $source -Filter '*.ipynb' -File |
             Where-Object { $_.Name -notin $excluded }

if (-not $notebooks) {
    throw "sync-shared: no notebooks found in '$source' after exclusions."
}

$drift = @()

foreach ($dest in $destinations) {
    if (-not (Test-Path $dest)) {
        if ($Check) {
            $drift += "MISSING DIR: $dest"
            continue
        }
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
    }
    foreach ($nb in $notebooks) {
        $target = Join-Path $dest $nb.Name
        $srcHash = (Get-FileHash $nb.FullName -Algorithm SHA256).Hash
        $tgtHash = if (Test-Path $target) { (Get-FileHash $target -Algorithm SHA256).Hash } else { $null }
        if ($srcHash -ne $tgtHash) {
            if ($Check) {
                $drift += "DRIFT: $target"
            } else {
                Copy-Item $nb.FullName $target -Force
                Write-Host "synced -> $target"
            }
        }
    }
}

if ($Check -and $drift.Count -gt 0) {
    Write-Host ""
    Write-Host "sync-shared: drift detected"
    $drift | ForEach-Object { Write-Host "  $_" }
    Write-Host ""
    Write-Host "Run scripts\sync-shared.ps1 to fix."
    exit 1
}

Write-Host ""
Write-Host "sync-shared: OK ($($notebooks.Count) notebook(s) x $($destinations.Count) destinations)"
if ($excluded) {
    Write-Host "  not mirrored: $($excluded -join ', ')"
}
