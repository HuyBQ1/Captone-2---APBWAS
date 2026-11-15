$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$backupDirectory = Join-Path $projectPath 'backups'
New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$containerFile = '/tmp/apbwas-' + $stamp + '.dump'
$outputFile = Join-Path $backupDirectory ('apbwas-' + $stamp + '.dump')
Push-Location -LiteralPath $projectPath
try {
    & docker compose exec -T postgres pg_dump -U apbwas -d apbwas -Fc --file $containerFile
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL backup failed.' }
    & docker compose cp ('postgres:' + $containerFile) $outputFile
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy the database backup.' }
    & docker compose exec -T postgres pg_restore --list $containerFile | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Backup archive validation failed.' }
    Write-Output ('Database backup saved: ' + $outputFile)
} finally {
    & docker compose exec -T postgres rm -f $containerFile
    Pop-Location
}
