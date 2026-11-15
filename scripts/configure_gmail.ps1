$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$envPath = Join-Path $projectPath '.env'
if (-not (Test-Path -LiteralPath $envPath)) { throw 'Create .env from .env.example first.' }
$clientId = (Read-Host 'Google OAuth Client ID').Trim()
if ($clientId -notmatch '^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$') { throw 'Invalid Google OAuth Client ID.' }
$secureSecret = Read-Host 'Google OAuth Client Secret (hidden input)' -AsSecureString
$secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSecret)
try {
    $clientSecret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)
    if ($clientSecret -notmatch '^[A-Za-z0-9_-]{10,200}$') { throw 'Invalid Google OAuth Client Secret.' }
    $contents = [IO.File]::ReadAllText($envPath)
    $senderMatch = [regex]::Match($contents, '(?m)^GMAIL_SENDER=(.*)\r?$')
    $sender = if ($senderMatch.Success) { $senderMatch.Groups[1].Value.Trim() } else { '' }
    if (-not $sender) { $sender = (Read-Host 'Gmail sender address').Trim() }
    if ($sender -notmatch '^[^\s@]+@[^\s@]+\.[^\s@]+$') { throw 'Invalid Gmail sender address.' }
    $keyMatch = [regex]::Match($contents, '(?m)^MAIL_ENCRYPTION_KEY=(.*)\r?$')
    $encryptionKey = if ($keyMatch.Success) { $keyMatch.Groups[1].Value.Trim().Trim('"', "'") } else { '' }
    if (-not $encryptionKey) {
        $randomBytes = New-Object byte[] 32
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($randomBytes) } finally { $rng.Dispose() }
        $encryptionKey = [Convert]::ToBase64String($randomBytes).Replace('+','-').Replace('/','_')
    }
    $values = [ordered]@{
        GMAIL_SENDER = $sender
        GMAIL_CLIENT_ID = $clientId
        GMAIL_CLIENT_SECRET = $clientSecret
        GMAIL_REDIRECT_URI = 'http://localhost:4180/mail/callback'
        MAIL_ENCRYPTION_KEY = $encryptionKey
    }
    foreach ($entry in $values.GetEnumerator()) {
        $pattern = '(?m)^' + [regex]::Escape($entry.Key) + '=.*\r?$'
        $line = $entry.Key + '=' + $entry.Value
        if ([regex]::IsMatch($contents,$pattern)) {
            $contents = [regex]::Replace($contents,$pattern,[Text.RegularExpressions.MatchEvaluator]{ param($match) $line })
        } else { $contents = $contents.TrimEnd() + "`n" + $line + "`n" }
    }
    [IO.File]::WriteAllText($envPath,$contents,(New-Object Text.UTF8Encoding($false)))
    Write-Host 'Gmail OAuth settings saved to the ignored backend .env file. No secrets displayed.'
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer)
    $clientSecret = $null
}
Push-Location -LiteralPath $projectPath
try {
    & docker compose up -d --force-recreate backend worker
    if ($LASTEXITCODE -ne 0) { throw 'Settings saved. Container reload failed; run docker compose up -d manually.' }
} finally { Pop-Location }
Write-Host 'Open http://localhost:4180/mail and choose Connect with Google.'
