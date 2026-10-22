# Verified, repeatable GitHub Release publication without GitHub Actions.
# Run from a fresh gh clone with write permission; no sensitive data required.
[CmdletBinding()]
param(
    [string]$Repository = 'gigabytegrove/carrier-smarthome-ha',
    [string]$ExpectedCommit = ''
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$manifestFile = Join-Path $root 'custom_components\carrier_smarthome\manifest.json'
$manifest = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
if ($manifest.domain -ne 'carrier_smarthome' -or $manifest.version -notmatch '^\d+\.\d+\.\d+$') {
    throw 'Manifest domain or release version invalid.'
}
$tag = 'v' + $manifest.version
$sha = (& git -C $root rev-parse HEAD | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[a-fA-F0-9]{40}$') { throw 'Not a valid Git checkout.' }
$remote = (& git -C $root remote get-url origin | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $remote -notmatch 'github\.com[:/]gigabytegrove/carrier-smarthome-ha(\.git)?$') {
    throw 'Not the expected Carrier SmartHome repository.'
}
if ($ExpectedCommit -and $ExpectedCommit -ne $sha) { throw 'Local checkout does not match expected source commit.' }
$head = (& gh api ('repos/' + $Repository + '/branches/main') --jq '.commit.sha' | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $sha) { throw 'Main changed or clone is stale. Refusing publication.' }
$existing = @(& gh release list --repo $Repository --limit 100 --json tagName --jq '.[].tagName')
if ($LASTEXITCODE -ne 0) { throw 'Could not list GitHub releases.' }
if ($existing -notcontains $tag) {
    $all = Get-Content -LiteralPath (Join-Path $root 'CHANGELOG.md') -Raw
    $header = '(?m)^##\s+(?:v)?' + [regex]::Escape($manifest.version) + '\b[^\r\n]*'
    $match = [regex]::Match($all, $header)
    if (-not $match.Success) { throw 'Current version must have detailed changelog entry.' }
    $after = $all.Substring($match.Index)
    $next = [regex]::Match($after.Substring($match.Length), '(?m)^##\s+')
    $notes = if ($next.Success) { $after.Substring(0, $match.Length + $next.Index) } else { $after }
    $notes += "`n`n## Install / update`nUse HACS -> Carrier SmartHome -> Download/Redownload and restart Home Assistant. Verify integration_manifest.version in diagnostics. Local HVAC control remains unverified; no Matter.`n"
    $notesPath = Join-Path $env:TEMP ('carrier-release-notes-' + [guid]::NewGuid().ToString('N') + '.md')
    try {
        Set-Content -LiteralPath $notesPath -Value $notes -Encoding UTF8
        & gh release create $tag --repo $Repository --target $sha --title ('Carrier SmartHome ' + $tag) --notes-file $notesPath
        if ($LASTEXITCODE -ne 0) { throw 'GitHub Release creation failed.' }
    }
    finally { Remove-Item -LiteralPath $notesPath -Force -ErrorAction SilentlyContinue }
}
$release = (& gh release view $tag --repo $Repository --json tagName,targetCommitish,isDraft --jq '{tag:.tagName,target:.targetCommitish,draft:.isDraft}' | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Release not verified.' }
$info = $release | ConvertFrom-Json
if ($info.tag -ne $tag -or $info.draft -eq $true -or $info.target -ne $sha) {
    throw 'Release exists but target or status differs from verified commit. Manual review required.'
}
Write-Host ('VERIFIED GITHUB RELEASE ' + $tag + ' @ ' + $sha) -ForegroundColor Green
