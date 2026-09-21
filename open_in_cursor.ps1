$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspace = Join-Path $here "GenomeSkeptic.code-workspace"
$cursor = Get-Command cursor -ErrorAction SilentlyContinue
if ($cursor) {
    Start-Process $cursor.Source -ArgumentList @($workspace)
    exit 0
}
$candidates = @(
    "$env:LOCALAPPDATA\Programs\cursor\Cursor.exe",
    "$env:LOCALAPPDATA\Programs\Cursor\Cursor.exe",
    "$env:ProgramFiles\Cursor\Cursor.exe"
)
foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
        Start-Process $candidate -ArgumentList @($workspace)
        exit 0
    }
}
Write-Host "Cursor was not found automatically. Open GenomeSkeptic.code-workspace from Cursor manually."
