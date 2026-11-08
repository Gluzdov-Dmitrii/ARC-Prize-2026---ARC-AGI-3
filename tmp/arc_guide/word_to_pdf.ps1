param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$inputDocx = (Resolve-Path -LiteralPath $InputPath).Path
$outputPdf = [System.IO.Path]::GetFullPath($OutputPath)
if ([System.IO.Path]::GetExtension($inputDocx) -ne '.docx') {
    throw 'Only task-created .docx input is supported by this adapter.'
}
if ([System.IO.Path]::GetExtension($outputPdf) -ne '.pdf') {
    throw 'OutputPath must end in .pdf.'
}
$outputParent = [System.IO.Path]::GetDirectoryName($outputPdf)
[System.IO.Directory]::CreateDirectory($outputParent) | Out-Null
$word = $null
$document = $null
$ownsInstance = $false
try {
    # CoCreateInstance makes a separate Word instance; never attach to a running
    # user application and never inspect or close an existing user's document.
    $word = New-Object -ComObject Word.Application
    if ($word.Documents.Count -ne 0) {
        throw 'Word returned an instance with open documents; refusing to use it.'
    }
    $ownsInstance = $true
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    # ConfirmConversions=false, ReadOnly=true, AddToRecentFiles=false.
    $document = $word.Documents.Open($inputDocx, $false, $true, $false)
    $document.Repaginate()
    $document.ExportAsFixedFormat($outputPdf, 17)
    if (!(Test-Path -LiteralPath $outputPdf -PathType Leaf)) {
        throw 'Word did not create the requested PDF.'
    }
    Write-Output ('Word exported PDF: ' + $outputPdf)
}
finally {
    try {
        if ($null -ne $document) {
            try {
                $document.Saved = $true
                $document.Close()
            }
            catch {
                Write-Warning ('Cleanup could not close its read-only render document: ' + $_.Exception.Message)
            }
            finally {
                [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) | Out-Null
            }
        }
    }
    finally {
        if ($null -ne $word) {
            try {
                if ($ownsInstance -and $word.Documents.Count -eq 0) {
                    $word.Quit()
                }
            }
            catch {
                Write-Warning ('Cleanup could not quit its empty Word instance: ' + $_.Exception.Message)
            }
            finally {
                [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) | Out-Null
            }
        }
    }
}
