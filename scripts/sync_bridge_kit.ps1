# =============================================================================
# sync_bridge_kit.ps1 — vendor the bridge installer into the POS app.
#
# Run this in POS_Core whenever the bridge is tagged. It:
#
#   1. checks out the requested tag in the bridge repo
#   2. builds the wheel
#   3. assembles the kit (installers + profiles + wheel)
#   4. zips it into alphax_pos_suite/public/bridge/
#   5. writes manifest.json with version + sha256
#
# After this, deploying the POS deploys the bridge. The shop never needs a
# route to GitHub.
#
# Deliberately NOT a git submodule: Frappe Cloud's app fetch does not
# reliably recurse submodules, and a missing submodule would fail silently
# at deploy time with an empty directory. A vendored zip plus a hash in
# the manifest fails loudly instead.
#
# Usage:
#   .\scripts\sync_bridge_kit.ps1 -BridgeRepo "E:\POS CORE\bridge-repo" -Tag v15.5.3
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string] $BridgeRepo,
    [Parameter(Mandatory=$true)] [string] $Tag,
    [string] $PosRepo = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'

$Dest = Join-Path $PosRepo "alphax_pos_suite\public\bridge"
$Work = Join-Path $env:TEMP ("alphax-kit-" + [guid]::NewGuid().ToString('N').Substring(0,8))

Write-Host ''
Write-Host '=== Vendoring AlphaX POS Bridge into the POS app ===' -ForegroundColor Cyan
Write-Host "  bridge repo : $BridgeRepo"
Write-Host "  tag         : $Tag"
Write-Host "  destination : $Dest"
Write-Host ''

if (-not (Test-Path (Join-Path $BridgeRepo '.git'))) {
    throw "Not a git repository: $BridgeRepo"
}

# --- 1. check out the tag ----------------------------------------------------
Push-Location $BridgeRepo
try {
    $dirty = git status --porcelain
    if ($dirty) { throw "Bridge repo has uncommitted changes. Commit or stash first." }

    $prevRef = (git rev-parse --abbrev-ref HEAD)
    if ($prevRef -eq 'HEAD') { $prevRef = (git rev-parse HEAD) }

    git checkout $Tag --quiet
    if ($LASTEXITCODE -ne 0) { throw "Tag $Tag not found in the bridge repo." }

    $version = (Select-String -Path "alphax_bridge\__init__.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
    Write-Host "Bridge source version: $version"

    if ($Tag -notmatch [regex]::Escape($version)) {
        Write-Host "WARNING: tag '$Tag' does not contain version '$version'." -ForegroundColor Yellow
        Write-Host "         The two drifted before. Check before shipping." -ForegroundColor Yellow
    }

    # --- 2. build the wheel --------------------------------------------------
    Write-Host 'Building the wheel...'
    if (Test-Path 'dist') { Remove-Item 'dist' -Recurse -Force }
    python -m pip install --upgrade build --quiet
    python -m build --wheel --outdir dist
    if ($LASTEXITCODE -ne 0) { throw 'wheel build failed' }

    $wheel = Get-ChildItem 'dist' -Filter '*.whl' | Select-Object -First 1
    if (-not $wheel) { throw 'no wheel produced' }
    Write-Host "  $($wheel.Name)"

    # --- 3. assemble the kit -------------------------------------------------
    New-Item -ItemType Directory -Force -Path $Work | Out-Null
    Copy-Item "packaging\kit\*" $Work -Recurse -Force

    # Profiles are canonical at the repo root. The kit's own copy drifts,
    # so overwrite it every time rather than trusting whatever was vendored.
    $kitProfiles = Join-Path $Work 'profiles'
    if (Test-Path $kitProfiles) { Remove-Item $kitProfiles -Recurse -Force }
    Copy-Item 'profiles' $kitProfiles -Recurse -Force

    Copy-Item $wheel.FullName $Work -Force

    # --- 4. zip into the POS app --------------------------------------------
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Get-ChildItem $Dest -Filter 'AlphaX-POS-Bridge-Setup-*.zip' | Remove-Item -Force

    $kitName = "AlphaX-POS-Bridge-Setup-$version.zip"
    $kitPath = Join-Path $Dest $kitName
    Compress-Archive -Path (Join-Path $Work '*') -DestinationPath $kitPath -Force
    $sha = (Get-FileHash $kitPath -Algorithm SHA256).Hash.ToLower()
    $size = (Get-Item $kitPath).Length

    # --- 5. manifest ---------------------------------------------------------
    [ordered]@{
        version    = $version
        kit_file   = $kitName
        sha256     = $sha
        size_bytes = $size
        source_tag = $Tag
        source_sha = (git rev-parse HEAD)
        built_at   = (Get-Date -Format 'o')
    } | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $Dest 'manifest.json') -Encoding UTF8

    Write-Host ''
    Write-Host '--- Vendored -------------------------------------------------' -ForegroundColor Green
    Write-Host ("  file   : {0}" -f $kitName)
    Write-Host ("  size   : {0:N0} bytes" -f $size)
    Write-Host ("  sha256 : {0}" -f $sha)
    Write-Host '--------------------------------------------------------------' -ForegroundColor Green
}
finally {
    if ($prevRef) { git checkout $prevRef --quiet 2>$null }
    Pop-Location
    if (Test-Path $Work) { Remove-Item $Work -Recurse -Force -ErrorAction SilentlyContinue }
}

Write-Host ''
Write-Host 'Next:' -ForegroundColor Cyan
Write-Host '  git add alphax_pos_suite/public/bridge'
Write-Host "  git commit -m `"vendor bridge $Tag into POS bundle`""
Write-Host ''
Write-Host 'The zip is a build artefact but SHOULD be committed - it is what' -ForegroundColor Gray
Write-Host 'Frappe Cloud serves to cashier stations. Keep exactly one.' -ForegroundColor Gray
