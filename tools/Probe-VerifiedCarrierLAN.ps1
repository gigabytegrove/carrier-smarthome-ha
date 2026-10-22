# Backwards-compatible wrapper. All local discovery is now in Probe-CarrierLocalDeep.ps1.
[CmdletBinding()]
param(
    [string]$ArchivePath,
    [string]$Suffix,
    [ValidateRange(5,120)][int]$MaxAgeMinutes = 30,
    [switch]$PlanOnly,
    [switch]$HttpFingerprint
)
$ErrorActionPreference = 'Stop'
$next = Join-Path $PSScriptRoot 'Probe-CarrierLocalDeep.ps1'
$argsForProbe = @{ MaxAgeMinutes = $MaxAgeMinutes }
if ($ArchivePath) { $argsForProbe.ArchivePath = $ArchivePath }
if ($Suffix) { $argsForProbe.MacSuffix = $Suffix }
if ($PlanOnly) { $argsForProbe.PlanOnly = $true }
# HTTP HEAD fingerprinting occurs automatically on open known HTTP listener ports.
& $next @argsForProbe
if (-not $?) { throw 'Carrier deep probe stopped. No old-IP fallback exists.' }
