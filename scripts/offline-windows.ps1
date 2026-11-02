# CI-only: block Internet access for a Python executable while a local check runs.
# Requires an administrator account on an ephemeral Windows runner.
param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string[]]$Arguments
)
$ErrorActionPreference = 'Stop'
$Python = (Resolve-Path $Python).Path
$profiles = @(Get-NetFirewallProfile | Select-Object Name, Enabled)
$rules = @()
$code = 1
try {
    if ((Get-Service mpssvc).Status -ne 'Running') { Start-Service mpssvc }
    foreach ($profile in $profiles) {
        Set-NetFirewallProfile -Profile $profile.Name -Enabled True
    }
    if (@(Get-NetFirewallProfile | Where-Object { $_.Enabled -ne 'True' }).Count -gt 0) {
        throw 'Pare-feu Windows non actif : execution hors reseau refusee.'
    }
    $programs = @($Python)
    $windowed = Join-Path (Split-Path $Python) 'pythonw.exe'
    if (Test-Path $windowed) { $programs += $windowed }
    foreach ($program in $programs) {
        $name = 'MAJIMeeting-test-offline-' + [guid]::NewGuid().ToString('N')
        $rules += $name
        New-NetFirewallRule -Name $name -DisplayName $name -Direction Outbound -Action Block `
            -Program $program -Enabled True -Profile Any | Out-Null
        $rule = Get-NetFirewallRule -Name $name
        if ($rule.Enabled -ne 'True' -or $rule.Action -ne 'Block') { throw 'Blocage reseau non actif.' }
    }
    & $Python @Arguments
    $code = $LASTEXITCODE
} finally {
    foreach ($name in $rules) { Remove-NetFirewallRule -Name $name -ErrorAction SilentlyContinue }
    foreach ($profile in $profiles) {
        Set-NetFirewallProfile -Profile $profile.Name -Enabled $profile.Enabled
    }
}
exit $code
