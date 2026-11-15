$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root '.test-tmp/word-qa'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$word.AutomationSecurity = 3
$results = @()
try {
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $root 'docs/company-word') -Filter '*.docx') {
        $document = $null
        try {
            $document = $word.Documents.Open($file.FullName, $false, $true, $false)
            $document.Repaginate()
            $pages = $document.ComputeStatistics(2)
            $pdf = Join-Path $out ($file.BaseName + '.pdf')
            $document.ExportAsFixedFormat($pdf, 17)
            $results += [PSCustomObject]@{file=$file.Name;pages=$pages;pdf=$pdf}
            Write-Output ($file.Name.Split('_')[0] + ': ' + $pages + ' pages')
        } finally {
            if ($null -ne $document) { $document.Close(0) }
        }
    }
} finally {
    $word.Quit()
}
$results | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $out 'render-results.json') -Encoding utf8
