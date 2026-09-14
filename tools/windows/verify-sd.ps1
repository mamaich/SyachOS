# Byte-compares the SD card against the image that was supposedly flashed.
# READ ONLY - never writes anything.
#
# Run from an ELEVATED PowerShell (Win+X -> Terminal (Admin)):
#   powershell -ExecutionPolicy Bypass -File T:\Dump\RG52Mini\android\verify-sd.ps1
#
# Raw disk access needs Administrator; Windows cannot mount these partitions
# (Rockchip GPT type GUIDs are not "Microsoft basic data").

param(
    [string]$Image = 'T:\Dump\RG52Mini\android\SyachOS-RG52Mini-V1.0.317m1.0.img',
    [int]$Disk = -1
)

$ErrorActionPreference = 'Stop'
function Fail($m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Fail "must be run as Administrator" }
if (-not (Test-Path $Image)) { Fail "image not found: $Image" }

# ------------------------------------------------------------- pick the disk
if ($Disk -lt 0) {
    $cands = @(Get-Disk | Where-Object { $_.BusType -eq 'USB' -and $_.Size -lt 400GB })
    if ($cands.Count -eq 0) { Fail "no removable USB disk under 400 GB found" }
    if ($cands.Count -gt 1) {
        $cands | Select-Object Number,FriendlyName,@{n='GB';e={[math]::Round($_.Size/1GB,1)}} | Format-Table -AutoSize | Out-String | Write-Host
        Fail "several candidates - rerun with -Disk <number>"
    }
    $Disk = $cands[0].Number
}
$d = Get-Disk -Number $Disk
Write-Host ("Comparing PhysicalDrive{0} '{1}' ({2} GB) against`n  {3}" -f `
    $Disk, $d.FriendlyName, [math]::Round($d.Size/1GB,1), $Image) -ForegroundColor Cyan

$img = [System.IO.File]::OpenRead($Image)
$dsk = New-Object System.IO.FileStream("\.\PhysicalDrive$Disk",'Open','Read','ReadWrite')
try {
    $CH  = 4194304
    $a = New-Object byte[] $CH
    $b = New-Object byte[] $CH
    $pos = 0; $bad = 0; $firstBad = -1; $badRanges = @()
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($pos -lt $img.Length) {
        $want = [Math]::Min($CH, $img.Length - $pos)
        $ra = 0; while ($ra -lt $want) { $n = $img.Read($a, $ra, $want - $ra); if ($n -le 0) { break }; $ra += $n }
        $rb = 0; while ($rb -lt $want) { $n = $dsk.Read($b, $rb, $want - $rb); if ($n -le 0) { break }; $rb += $n }
        if ($rb -lt $want) { Fail "short read from disk at offset $pos (got $rb of $want) - card failing or smaller than image" }

        $diffHere = $false
        for ($i = 0; $i -lt $want; $i++) {
            if ($a[$i] -ne $b[$i]) {
                $bad++
                if ($firstBad -lt 0) { $firstBad = $pos + $i }
                if (-not $diffHere) { $badRanges += ($pos + $i); $diffHere = $true }
                if ($bad -gt 5000000) { break }
            }
        }
        $pos += $want
        if ($sw.Elapsed.TotalSeconds -ge 3) {
            Write-Host ("  {0,6:N0} MB / {1,6:N0} MB   mismatching bytes so far: {2:N0}" -f ($pos/1MB), ($img.Length/1MB), $bad)
            $sw.Restart()
        }
    }
    Write-Host ""
    if ($bad -eq 0) {
        Write-Host "IDENTICAL - the card holds exactly this image. The flash is not the problem." -ForegroundColor Green
    } else {
        Write-Host ("MISMATCH: {0:N0} differing bytes, first at offset {1} (0x{1:X})" -f $bad, $firstBad) -ForegroundColor Red
        $r = $badRanges | Select-Object -First 12
        Write-Host ("first differing chunks at: " + ($r -join ', '))
        Write-Host "-> the card does not hold the image: flash did not complete, or the card is failing."
    }
} finally { $img.Close(); $dsk.Close() }
