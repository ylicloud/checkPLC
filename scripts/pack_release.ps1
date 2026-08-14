# checkPLC pack for another PC
# Usage: double-click pack.bat in repo root, or: .\scripts\pack_release.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step($msg, $color = "White") {
    Write-Host $msg -ForegroundColor $color
}

# 同事装机需要的根文件 / 目录（不要整仓拷贝）
$RootFiles = @(
    "setup.bat",
    "run.bat",
    "pack.bat",
    "README.md",
    "requirements.txt",
    ".gitignore"
)
$RootDirs = @(
    "web",
    "configs",
    "scripts",
    "docs",
    "plc",
    "workspace",
    "tools"
)

# 这些目录名在任意层级都跳过
$SkipDirNames = [System.Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
@(
    ".git", ".venv", ".codegraph", ".vci", ".idea", ".vscode",
    "__pycache__", ".pytest_cache",
    "bin", "obj",
    "Logs", "SearchIndex"
) | ForEach-Object { [void]$SkipDirNames.Add($_) }

function Test-SkipPath([string]$fullPath) {
    $rel = $fullPath.Substring($Root.Length).TrimStart("\", "/")
    $parts = $rel.Split([char[]]@("\", "/"), [StringSplitOptions]::RemoveEmptyEntries)
    foreach ($p in $parts) {
        if ($SkipDirNames.Contains($p)) { return $true }
    }
    $leaf = $parts[-1]
    if ($leaf -match '\.(pyc|pyo|log)$') { return $true }
    if ($leaf -like "checkPLC-*.zip") { return $true }
    # 临时 AML 不打进包；示例 AML 保留
    if ($leaf -like "*.aml" -and ($rel -notmatch [regex]::Escape("tools\tia-openness-export\samples\"))) {
        return $true
    }
    if ($leaf -like "_tmp_*.py") { return $true }
    return $false
}

Write-Host ""
Write-Step "========================================" "Cyan"
Write-Step "  checkPLC pack" "Cyan"
Write-Step "========================================" "Cyan"
Write-Host ""

$missing = @()
foreach ($f in $RootFiles) {
    if ($f -eq "pack.bat") { continue }
    if (-not (Test-Path (Join-Path $Root $f))) { $missing += $f }
}
foreach ($d in $RootDirs) {
    if (-not (Test-Path (Join-Path $Root $d))) { $missing += $d }
}
if ($missing.Count -gt 0) {
    Write-Step "ERROR: missing: $($missing -join ', ')" "Red"
    exit 1
}

$files = New-Object System.Collections.Generic.List[System.IO.FileInfo]
foreach ($name in $RootFiles) {
    $p = Join-Path $Root $name
    if (Test-Path -LiteralPath $p -PathType Leaf) {
        $files.Add((Get-Item -LiteralPath $p))
    }
}
foreach ($dirName in $RootDirs) {
    $dir = Join-Path $Root $dirName
    Get-ChildItem -LiteralPath $dir -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
        if (-not (Test-SkipPath $_.FullName)) {
            $files.Add($_)
        }
    }
}

if ($files.Count -lt 1) {
    Write-Step "ERROR: no files to pack" "Red"
    exit 1
}

$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$outDir = Join-Path $Root "dist"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$zipPath = Join-Path $outDir "checkPLC-$stamp.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Write-Step "...  Packing $($files.Count) files" "Yellow"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$zip = $null
try {
    $zip = [System.IO.Compression.ZipFile]::Open(
        $zipPath,
        [System.IO.Compression.ZipArchiveMode]::Create
    )
    foreach ($file in $files) {
        $rel = $file.FullName.Substring($Root.Length).TrimStart("\", "/")
        $entryName = ("checkPLC/" + ($rel -replace "\\", "/"))
        $entry = $zip.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Optimal)
        $entry.LastWriteTime = $file.LastWriteTime
        $src = $null
        $dest = $null
        try {
            $src = [System.IO.File]::OpenRead($file.FullName)
            $dest = $entry.Open()
            $src.CopyTo($dest)
        }
        finally {
            if ($dest) { $dest.Dispose() }
            if ($src) { $src.Dispose() }
        }
    }
}
finally {
    if ($zip) { $zip.Dispose() }
}

$zipItem = Get-Item -LiteralPath $zipPath
$sizeMb = [math]::Round($zipItem.Length / 1MB, 2)

Write-Host ""
Write-Step "========================================" "Green"
Write-Step "  Pack complete" "Green"
Write-Step "========================================" "Green"
Write-Host ""
Write-Step "Zip : $($zipItem.FullName)" "Cyan"
Write-Step "Size: $sizeMb MB  ($($files.Count) files)" "Cyan"
Write-Host ""
Write-Step "Send this zip. Do not include .venv / .git / TIA projects." "Yellow"
Write-Step "On the other PC: unzip -> install Python 3.10+ (Add to PATH) -> setup.bat -> run.bat" "Yellow"
Write-Host ""
