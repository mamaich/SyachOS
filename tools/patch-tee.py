#!/usr/bin/env python3
"""Stops the endless tee-supplicant respawn in the image.

OP-TEE is not declared in the device tree, so /dev/tee* never appears,
tee-supplicant exits with status 1 and init restarts it forever. Nothing
depends on it: keymint and gatekeeper are the software implementations.

Two things are needed, and the second is easy to miss:
  * comment out the explicit "start" in the `on post-fs` trigger;
  * add `disabled` to the service - otherwise `class_start core` starts it
    anyway, whatever the triggers say.

The service definition itself stays, so "start tee-supplicant" by name still
works if it is ever needed.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = A + "SyachOS-RG52Mini-V1.0.317-aic8800-wifi-bt.img"
P5_OFF, P5_LEN = 1698693120, 267046912
RC = "/etc/init/init.tee-supplicant.rc"

tmp = tempfile.mkdtemp()
part = os.path.join(tmp, "p5.img")
with open(IMG, "rb") as f:
    f.seek(P5_OFF)
    open(part, "wb").write(f.read(P5_LEN))

cur = os.path.join(tmp, "rc")
subprocess.run(["debugfs", "-R", "dump %s %s" % (RC, cur), part],
               capture_output=True, check=True)
data = open(cur, "rb").read()
print("--- было (%d байт):" % len(data)); print(data.decode())

out = data
if b"\n    start tee-supplicant" in out:
    out = out.replace(b"\n    start tee-supplicant", b"\n#   start tee-supplicant")
if b"\n    disabled\n" not in out:
    if b"\n    class core\n" not in out:
        sys.exit("не нашёл 'class core' - структура .rc другая")
    out = out.replace(b"\n    class core\n", b"\n    class core\n    disabled\n")

if out == data:
    sys.exit("уже отключено, делать нечего")

new = os.path.join(tmp, "rc.new")
open(new, "wb").write(out)

script = ("rm %s\ncd /etc/init\nwrite %s init.tee-supplicant.rc\n"
          "sif %s mode 0100644\nquit\n" % (RC, new, RC))
subprocess.run(["debugfs", "-w", "-f", "-", part], input=script,
               capture_output=True, text=True)
r = subprocess.run(["e2fsck", "-fp", part], capture_output=True, text=True)
print("e2fsck:", r.stdout.strip().splitlines()[-1])

back = os.path.join(tmp, "back")
subprocess.run(["debugfs", "-R", "dump %s %s" % (RC, back), part],
               capture_output=True, check=True)
got = open(back, "rb").read()
print("--- стало (%d байт):" % len(got)); print(got.decode())
if got != out:
    sys.exit("записалось неверно")
assert b"    disabled" in got and b"\n#   start tee-supplicant" in got

with open(IMG, "r+b") as f:
    f.seek(P5_OFF)
    f.write(open(part, "rb").read())
    f.flush()
print("образ обновлён")
