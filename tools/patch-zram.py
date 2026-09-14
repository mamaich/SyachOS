#!/usr/bin/env python3
"""Raises zram swap from 50% to 100% of RAM in the image.

Edits the single zram line of /vendor/etc/fstab.rk30board inside the vendor
partition. The replacement is the same byte length (one space of padding is
dropped), so no ext4 block is reallocated and no metadata changes at all -
the bytes are patched where they lie.

Careful: "zramsize=50%" also appears in the /vendor/etc/fstab_ext*.cfg
templates, so the whole line is matched, not just the option.
"""
import subprocess, sys, tempfile, os

IMG = "/mnt/t/Dump/RG52Mini/android/SyachOS-RG52Mini-V1.0.317-aic8800-wifi-bt.img"
P5_OFF, P5_LEN = 1698693120, 267046912
FSTAB = "/etc/fstab.rk30board"

# pull the current file out of the image so the line is matched exactly
tmp = tempfile.mkdtemp()
part = os.path.join(tmp, "p5.img")
with open(IMG, "rb") as f:
    f.seek(P5_OFF)
    blob = f.read(P5_LEN)
open(part, "wb").write(blob)
out = os.path.join(tmp, "fstab")
subprocess.run(["debugfs", "-R", "dump %s %s" % (FSTAB, out), part],
               capture_output=True, check=True)
cur = open(out, "rb").read()
print("fstab.rk30board: %d байт" % len(cur))

lines = [l for l in cur.split(b"\n") if b"zram0" in l]
if len(lines) != 1:
    sys.exit("ожидал одну строку с zram0, нашёл %d" % len(lines))
old = lines[0]
if b"zramsize=100%" in old:
    sys.exit("уже 100%, делать нечего")
if b" zramsize=50%" not in old:
    sys.exit("не нашёл ' zramsize=50%' в строке")
new = old.replace(b" zramsize=50%", b"zramsize=100%")   # -1 пробел, +1 символ
if len(new) != len(old):
    sys.exit("длина строки изменилась")

n = blob.count(old)
if n != 1:
    sys.exit("строка встречается в разделе %d раз - отказываюсь писать" % n)
at = blob.find(old)
print("строка найдена по смещению %d внутри vendor" % at)

with open(IMG, "r+b") as f:
    f.seek(P5_OFF + at)
    f.write(new)
    f.flush()

# перечитать раздел и убедиться через файловую систему, а не по сырым байтам
with open(IMG, "rb") as f:
    f.seek(P5_OFF)
    open(part, "wb").write(f.read(P5_LEN))
subprocess.run(["debugfs", "-R", "dump %s %s" % (FSTAB, out), part],
               capture_output=True, check=True)
back = open(out, "rb").read()
assert len(back) == len(cur), "размер файла изменился"
line = [l for l in back.split(b"\n") if b"zram0" in l][0]
print("стало:", line.decode())
assert b"zramsize=100%" in line
r = subprocess.run(["e2fsck", "-fn", part], capture_output=True, text=True)
print("e2fsck:", r.stdout.strip().splitlines()[-1])
assert r.returncode == 0, "e2fsck недоволен"
os.remove(part); os.remove(out); os.rmdir(tmp)
print("OK")
