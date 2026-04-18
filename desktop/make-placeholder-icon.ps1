Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap 1024, 1024
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = 'AntiAlias'
$g.TextRenderingHint = 'AntiAliasGridFit'
$g.Clear([System.Drawing.Color]::FromArgb(34, 102, 204))
$font = New-Object System.Drawing.Font('Segoe UI', 360, [System.Drawing.FontStyle]::Bold)
$brush = [System.Drawing.Brushes]::White
$sf = New-Object System.Drawing.StringFormat
$sf.Alignment = [System.Drawing.StringAlignment]::Center
$sf.LineAlignment = [System.Drawing.StringAlignment]::Center
$rect = New-Object System.Drawing.RectangleF(0, 0, 1024, 1024)
$g.DrawString('PCA', $font, $brush, $rect, $sf)
$bmp.Save('app-icon.png', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
Get-Item app-icon.png | Format-List FullName, Length
