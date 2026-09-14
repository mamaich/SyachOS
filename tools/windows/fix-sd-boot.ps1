# Recovers the RG52 Mini SD card after a bad extlinux TIMEOUT value.
#
# Run from an ELEVATED PowerShell (Win+X -> Terminal (Admin)):
#   powershell -ExecutionPolicy Bypass -File T:\Dump\RG52Mini\android\fix-sd-boot.ps1
#
# Windows cannot mount the card (Rockchip GPT type GUIDs are not "basic data"),
# so this works on the raw disk: it finds the card by its GPT partition name
# dArkOS_Fat, locates extlinux.conf inside that FAT partition and rewrites the
# file in place, padded to the very same byte length so the FAT directory
# entry stays valid. Only the touched 512-byte sectors are written back.

$ErrorActionPreference = 'Stop'

function Fail($m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Fail "must be run as Administrator" }

# TIMEOUT 10 = 1.0 s. U-Boot does timeout/10 as integer division and treats 0
# as "wait forever", which is exactly what bricked the boot with TIMEOUT 1.
$NEW = @"
DEFAULT Android13
TIMEOUT 10
MENU TITLE RG52Mini Android 13 (V40)

LABEL Android13
    MENU LABEL Android 13
    LINUX /Image
    FDT /rk3562-rg52mini.dtb
    INITRD /initrd.gz
    APPEND console=ttyFIQ0,1500000 console=tty1 earlycon=uart8250,mmio32,0xff210000 firmware_class.path=/vendor/lib/firmware init=/init rootwait ro loop.max_part=7 8250.nr_uarts=10 storagemedia=sd androidboot.hardware=rk30board androidboot.boot_devices=ff880000.mmc androidboot.storagemedia=sd androidboot.mode=normal androidboot.force_normal_boot=1 androidboot.veritymode=disabled printk.devkmsg=on quiet loglevel=4 fbcon=rotate:1 androidboot.selinux=permissive
"@ -replace "`r`n", "`n"

# ---------------------------------------------------------------- find card
$cand = @()
foreach ($d in (Get-Disk | Where-Object { $_.PartitionStyle -eq 'GPT' -and $_.Size -lt 400GB })) {
    $probe = $null
    try {
        $probe = New-Object System.IO.FileStream("\.\PhysicalDrive$($d.Number)",'Open','Read','ReadWrite')
        $ss = [int]$d.LogicalSectorSize
        $b  = New-Object byte[] $ss
        $null = $probe.Seek([int64]$ss, 'Begin'); $null = $probe.Read($b, 0, $ss)
        if ([System.Text.Encoding]::ASCII.GetString($b,0,8) -ne 'EFI PART') { continue }
        $pteLba = [BitConverter]::ToUInt64($b,72)
        $nPart  = [BitConverter]::ToUInt32($b,80)
        $pSz    = [BitConverter]::ToUInt32($b,84)
        $tbl    = New-Object byte[] ($nPart * $pSz)
        $null = $probe.Seek([int64]$pteLba * $ss, 'Begin'); $null = $probe.Read($tbl, 0, $tbl.Length)
        for ($i = 0; $i -lt $nPart; $i++) {
            $o = $i * $pSz
            $name = [System.Text.Encoding]::Unicode.GetString($tbl, $o + 56, 72).TrimEnd([char]0)
            if ($name -eq 'dArkOS_Fat') {
                $start = [BitConverter]::ToUInt64($tbl, $o + 32)
                $end   = [BitConverter]::ToUInt64($tbl, $o + 40)
                $cand += [pscustomobject]@{
                    Disk = $d.Number; Name = $d.FriendlyName; Sector = $ss
                    Offset = [int64]($start * $ss); Length = [int]($end - $start + 1) * $ss
                }
            }
        }
    } catch { } finally { if ($probe) { $probe.Close() } }
}

if ($cand.Count -eq 0) { Fail "no disk with a dArkOS_Fat partition found (card inserted?)" }
if ($cand.Count -gt 1) { Fail "more than one candidate disk - refusing to guess" }
$c = $cand[0]
Write-Host ("Card: PhysicalDrive{0} '{1}' | dArkOS_Fat at offset {2}, {3} MB, sector {4}" -f `
    $c.Disk, $c.Name, $c.Offset, [math]::Round($c.Length/1MB), $c.Sector) -ForegroundColor Cyan

# ------------------------------------------------------------------ do work
$fs = New-Object System.IO.FileStream("\.\PhysicalDrive$($c.Disk)",'Open','ReadWrite','ReadWrite')
try {
    $buf  = New-Object byte[] $c.Length
    $null = $fs.Seek($c.Offset, 'Begin')
    $read = 0
    while ($read -lt $buf.Length) {
        $n = $fs.Read($buf, $read, [Math]::Min(4194304, $buf.Length - $read))
        if ($n -le 0) { break }
        $read += $n
    }
    Write-Host "read $read bytes"

    # Latin1 keeps byte index == char index, and IndexOf is native (fast).
    $L1  = [System.Text.Encoding]::GetEncoding(28591)
    $all = $L1.GetString($buf, 0, $read)

    $hits = @()
    $pos  = 0
    while ($true) {
        $k = $all.IndexOf('DEFAULT Android13', $pos)
        if ($k -lt 0) { break }
        $hits += $k
        $pos = $k + 1
    }
    Write-Host "extlinux.conf copies found: $($hits.Count)"

    $target = -1
    foreach ($h in $hits) {
        $txt  = $all.Substring($h, [Math]::Min(900, $all.Length - $h))
        $head = ($txt.Substring(0, [Math]::Min(120, $txt.Length)) -replace "`n", ' | ')
        Write-Host ("  at {0}: {1}" -f $h, $head)
        if ($txt -match "TIMEOUT\s+1(\r?\n)") { $target = $h }
    }
    if ($target -lt 0) { Fail "no copy with 'TIMEOUT 1' found - maybe already fixed" }

    $txt    = $all.Substring($target, [Math]::Min(1024, $all.Length - $target))
    $marker = 'androidboot.selinux=permissive'
    $endIdx = $txt.IndexOf($marker)
    if ($endIdx -lt 0) { Fail "end of APPEND line not found" }
    $oldLen = $endIdx + $marker.Length
    while ($oldLen -lt $txt.Length -and ($txt[$oldLen] -eq "`n" -or $txt[$oldLen] -eq "`r")) { $oldLen++ }
    Write-Host "file to replace: $oldLen bytes at partition offset $target"

    $newBytes = [System.Text.Encoding]::ASCII.GetBytes($NEW)
    if ($newBytes.Length -gt $oldLen) { Fail "new text longer than old ($($newBytes.Length) > $oldLen)" }
    $pad = New-Object byte[] $oldLen
    [Array]::Copy($newBytes, 0, $pad, 0, $newBytes.Length)
    for ($i = $newBytes.Length; $i -lt $oldLen; $i++) { $pad[$i] = 0x0A }   # trailing newlines
    [Array]::Copy($pad, 0, $buf, $target, $oldLen)

    $ss    = $c.Sector
    $from  = [int]([math]::Floor($target / $ss) * $ss)
    $to    = [int]([math]::Ceiling(($target + $oldLen) / $ss) * $ss)
    $len   = $to - $from
    $chunk = New-Object byte[] $len
    [Array]::Copy($buf, $from, $chunk, 0, $len)
    $null = $fs.Seek($c.Offset + $from, 'Begin')
    $fs.Write($chunk, 0, $len)
    $fs.Flush($true)
    Write-Host "wrote $len bytes at disk offset $($c.Offset + $from)" -ForegroundColor Green

    $chk  = New-Object byte[] $len
    $null = $fs.Seek($c.Offset + $from, 'Begin')
    $null = $fs.Read($chk, 0, $len)
    $back = [System.Text.Encoding]::ASCII.GetString($chk, $target - $from, $oldLen)
    Write-Host "--- content on the card now ---" -ForegroundColor Cyan
    Write-Host $back.TrimEnd()
    Write-Host "-------------------------------" -ForegroundColor Cyan
    if ($back -like '*TIMEOUT 10*') {
        Write-Host "DONE. Eject the card and power the device on." -ForegroundColor Green
    } else {
        Fail "verification failed"
    }
} finally { $fs.Close() }
