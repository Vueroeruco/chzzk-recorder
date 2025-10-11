$ErrorActionPreference = 'Stop'
param(
  [int]$IntervalSeconds = 5
)

function Get-LatestTsFile {
  Get-ChildItem -Recurse -File "chzzk_recorder\recordings" -Filter *.ts |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
}

while ($true) {
  $f = Get-LatestTsFile
  if ($null -ne $f) {
    $snap = Join-Path $f.DirectoryName ("{0}_view.ts" -f ($f.BaseName))
    try {
      Copy-Item -LiteralPath $f.FullName -Destination $snap -Force
      Write-Host ("[{0}] Snapshot -> {1}" -f (Get-Date), $snap)
    } catch {
      Write-Warning "Snapshot failed: $($_.Exception.Message)"
    }
  } else {
    Write-Host ("[{0}] No TS file found yet" -f (Get-Date))
  }
  Start-Sleep -Seconds $IntervalSeconds
}

