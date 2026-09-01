param(
    [string]$BlenderExe = $env:BLENDER_EXE
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $projectRoot 'source\simple_todo'
$outputDir = Join-Path $projectRoot 'dist'
$packageTest = Join-Path $projectRoot 'tests\test_package_contents.py'

if ([string]::IsNullOrWhiteSpace($BlenderExe)) {
    $blenderCommand = Get-Command blender -ErrorAction SilentlyContinue
    if ($null -ne $blenderCommand) {
        $BlenderExe = $blenderCommand.Source
    }
}

if (
    [string]::IsNullOrWhiteSpace($BlenderExe) -or
    -not (Test-Path -LiteralPath $BlenderExe -PathType Leaf)
) {
    throw 'Blender was not found. Pass -BlenderExe or set BLENDER_EXE.'
}

if (-not (Test-Path -LiteralPath $outputDir -PathType Container)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

# Use Blender's official validation and build commands to create the package.
& $BlenderExe --factory-startup --command extension validate $sourceDir
if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    throw "Extension validation failed with exit code $LASTEXITCODE."
}

& $BlenderExe --factory-startup --command extension build `
    --source-dir $sourceDir `
    --output-dir $outputDir
if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    throw "Extension build failed with exit code $LASTEXITCODE."
}

python -X utf8 $packageTest
if ($LASTEXITCODE -ne 0) {
    throw "Package content validation failed with exit code $LASTEXITCODE."
}
