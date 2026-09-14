#!/usr/bin/env python3
"""Lets the speaker amplifier sleep: standby time 600000 ms -> 3000 ms.

With the shipped value AudioFlinger keeps the output stream open for ten
minutes, so the DAC is never muted, so the external amplifier GPIO is never
released and it amplifies every power-rail glitch. 3000 ms is the AOSP default.

Only useful together with spk-mute-delay-ms in the DTB (patch-quiet.py):
without the delay a short standby just turns a constant hiss into frequent
clicks.

The value shrinks the file by two bytes, so the file is rewritten with debugfs
rather than patched in place.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = A + "SyachOS-RG52Mini-V1.0.317-aic8800-wifi-bt.img"
P5_OFF, P5_LEN = 1698693120, 267046912
OLD = b"ro.audio.flinger_standbytime_ms=600000"
NEW = b"ro.audio.flinger_standbytime_ms=3000"

tmp = tempfile.mkdtemp()
part = os.path.join(tmp, "p5.img")
with open(IMG, "rb") as f:
    f.seek(P5_OFF)
    open(part, "wb").write(f.read(P5_LEN))

cur = os.path.join(tmp, "build.prop")
subprocess.run(["debugfs", "-R", "dump /build.prop %s" % cur, part],
               capture_output=True, check=True)
data = open(cur, "rb").read()
print("build.prop: %d байт" % len(data))
if NEW in data:
    sys.exit("уже 3000, делать нечего")
if data.count(OLD) != 1:
    sys.exit("строка встречается %d раз" % data.count(OLD))

out = data.replace(OLD, NEW)
assert len(out) == len(data) - 2
if len(out.splitlines()) != len(data.splitlines()):
    sys.exit("число строк изменилось")
new = os.path.join(tmp, "build.prop.new")
open(new, "wb").write(out)

script = "rm /build.prop\ncd /\nwrite %s build.prop\nsif /build.prop mode 0100644\nquit\n" % new
subprocess.run(["debugfs", "-w", "-f", "-", part], input=script,
               capture_output=True, text=True)
r = subprocess.run(["e2fsck", "-fp", part], capture_output=True, text=True)
print("e2fsck:", r.stdout.strip().splitlines()[-1])

back = os.path.join(tmp, "back")
subprocess.run(["debugfs", "-R", "dump /build.prop %s" % back, part],
               capture_output=True, check=True)
if open(back, "rb").read() != out:
    sys.exit("записалось неверно")
print("проверено через ФС, строка:",
      [l for l in out.split(b"\n") if b"standbytime" in l][0].decode())

with open(IMG, "r+b") as f:
    f.seek(P5_OFF)
    f.write(open(part, "rb").read())
    f.flush()
print("образ обновлён")
