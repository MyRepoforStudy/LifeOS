<#
.SYNOPSIS
    Draws the PWA icons (PNG) into web\public\icons with System.Drawing.

        powershell -ExecutionPolicy Bypass -File .\web\scripts\make-icons.ps1

    The design matches web\public\favicon.svg: a graphite tile, a gold ring and an "L".
#>
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$outDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'public\icons'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function New-RoundedPath([float]$size, [float]$radius) {
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $radius * 2
    $path.AddArc(0, 0, $d, $d, 180, 90)
    $path.AddArc($size - $d, 0, $d, $d, 270, 90)
    $path.AddArc($size - $d, $size - $d, $d, $d, 0, 90)
    $path.AddArc(0, $size - $d, $d, $d, 90, 90)
    $path.CloseFigure()
    return $path
}

function Save-Icon([int]$size, [string]$name, [bool]$rounded, [float]$contentScale) {
    $bitmap = New-Object System.Drawing.Bitmap $size, $size
    $g = [System.Drawing.Graphics]::FromImage($bitmap)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.Clear([System.Drawing.Color]::Transparent)

    $background = New-Object System.Drawing.Drawing2D.LinearGradientBrush (
        (New-Object System.Drawing.Point 0, 0),
        (New-Object System.Drawing.Point $size, $size),
        [System.Drawing.ColorTranslator]::FromHtml('#1c2129'),
        [System.Drawing.ColorTranslator]::FromHtml('#0b0d11'))
    if ($rounded) {
        $g.FillPath($background, (New-RoundedPath $size ($size * 14 / 64)))
    } else {
        $g.FillRectangle($background, 0, 0, $size, $size)
    }

    # Content is drawn in 64-unit coordinates, scaled and centered.
    $unit = $size / 64 * $contentScale
    $offset = ($size - 64 * $unit) / 2
    $gold = New-Object System.Drawing.Drawing2D.LinearGradientBrush (
        (New-Object System.Drawing.PointF 0, ($offset + 11 * $unit)),
        (New-Object System.Drawing.PointF 0, ($offset + 53 * $unit)),
        [System.Drawing.ColorTranslator]::FromHtml('#ffd27a'),
        [System.Drawing.ColorTranslator]::FromHtml('#e09a2b'))

    $ring = New-Object System.Drawing.Pen $gold, (3.5 * $unit)
    $g.DrawEllipse($ring, $offset + 11 * $unit, $offset + 11 * $unit, 42 * $unit, 42 * $unit)

    $letter = New-Object System.Drawing.Pen $gold, (5 * $unit)
    $letter.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $letter.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $letter.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
    $points = [System.Drawing.PointF[]]@(
        (New-Object System.Drawing.PointF ($offset + 26 * $unit), ($offset + 20 * $unit)),
        (New-Object System.Drawing.PointF ($offset + 26 * $unit), ($offset + 44 * $unit)),
        (New-Object System.Drawing.PointF ($offset + 39 * $unit), ($offset + 44 * $unit))
    )
    $g.DrawLines($letter, $points)

    $target = Join-Path $outDir $name
    $bitmap.Save($target, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose()
    $bitmap.Dispose()
    Write-Host "wrote $target"
}

Save-Icon 192 'icon-192.png' $true 1.0
Save-Icon 512 'icon-512.png' $true 1.0
# Maskable icons are cropped by the OS: keep the emblem inside the central safe zone.
Save-Icon 512 'icon-maskable-512.png' $false 0.8
# iOS rounds the corners itself and expects an opaque square.
Save-Icon 180 'apple-touch-icon.png' $false 0.9
