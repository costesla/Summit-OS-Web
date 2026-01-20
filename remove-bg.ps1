
Add-Type -AssemblyName System.Drawing

$sourcePath = "c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\public\source-car.png"
$destPath = "c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\public\hero-car.png"

$image = [System.Drawing.Bitmap]::FromFile($sourcePath)
$newImage = New-Object System.Drawing.Bitmap($image.Width, $image.Height)
$graphics = [System.Drawing.Graphics]::FromImage($newImage)

# Draw the original image onto the new one
$graphics.DrawImage($image, 0, 0, $image.Width, $image.Height)

# Loop through pixels to replace black with transparent
# A simple threshold approach
for ($x = 0; $x -lt $newImage.Width; $x++) {
    for ($y = 0; $y -lt $newImage.Height; $y++) {
        $pixel = $newImage.GetPixel($x, $y)
        # Check if pixel is dark (approx black)
        if ($pixel.R -lt 20 -and $pixel.G -lt 20 -and $pixel.B -lt 20) {
            $newImage.SetPixel($x, $y, [System.Drawing.Color]::Transparent)
        }
    }
}

$newImage.Save($destPath, [System.Drawing.Imaging.ImageFormat]::Png)

$graphics.Dispose()
$image.Dispose()
$newImage.Dispose()

Write-Host "Background removed and saved to $destPath"
