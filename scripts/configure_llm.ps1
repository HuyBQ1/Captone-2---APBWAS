$ErrorActionPreference = 'Stop'
$llmProject = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$llmEnvPath = Join-Path $llmProject '.env'
if (-not (Test-Path -LiteralPath $llmEnvPath)) { throw 'Create .env from .env.example first.' }
$llmText = [IO.File]::ReadAllText($llmEnvPath)
function Read-LlmSetting([string]$settingName) {
    $settingMatch = [regex]::Match($llmText, '(?m)^' + [regex]::Escape($settingName) + '\s*=\s*([^\r\n]*)')
    if ($settingMatch.Success) { return $settingMatch.Groups[1].Value.Trim().Trim('"').Trim("'") }
    return ''
}
$llmKey = Read-LlmSetting 'LLM_ENCRYPTION_KEY'
if (-not $llmKey) {
    # Preserve any existing ciphertext that uses the Gmail-key fallback.
    $llmKey = Read-LlmSetting 'MAIL_ENCRYPTION_KEY'
    if (-not $llmKey) {
        $llmBytes = New-Object byte[] 32
        $llmRandom = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $llmRandom.GetBytes($llmBytes) } finally { $llmRandom.Dispose() }
        $llmKey = [Convert]::ToBase64String($llmBytes).Replace('+','-').Replace('/','_')
    }
    if ([regex]::IsMatch($llmText, '(?m)^LLM_ENCRYPTION_KEY\s*=')) {
        $llmText = [regex]::Replace($llmText, '(?m)^LLM_ENCRYPTION_KEY\s*=.*$', ('LLM_ENCRYPTION_KEY=' + $llmKey))
    } else { $llmText = $llmText.TrimEnd() + "`r`nLLM_ENCRYPTION_KEY=" + $llmKey + "`r`n" }
    [IO.File]::WriteAllText($llmEnvPath, $llmText, (New-Object Text.UTF8Encoding($false)))
}
Write-Output 'LLM encryption configured in ignored .env. No key displayed. Keep a secure backup of this encryption key.'
Push-Location -LiteralPath $llmProject
try {
    & docker compose up -d --no-deps backend worker
    if ($LASTEXITCODE -ne 0) { throw 'Could not restart backend/worker.' }
} finally { Pop-Location }
Write-Output 'Open http://localhost:4180/models as Admin to add a provider.'
