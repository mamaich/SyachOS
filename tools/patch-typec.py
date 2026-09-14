#!/usr/bin/env python3
"""Чинит USB host: кладёт в образ DTB с контроллером Type-C HUSB311.

Заменяет DTB целиком, поэтому выполняется ПОСЛЕ patch-quiet.py и отменяет
установленный им DTB: rk3562-rg52mini-typec.dtb собран из
rk3562-rg52mini-spkdelay.dtb, то есть уже содержит spk-mute-delay-ms.

Сам DTB собирает mkypec: см. mktypec.py.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = A + "SyachOS-RG52Mini-V1.0.317m1.0.img"
DTB = A + "rk3562-rg52mini-typec.dtb"
P3_OFF, P3_LEN = 16777216, 103809024

if not os.path.exists(DTB):
    sys.exit("нет %s - сначала mktypec.py" % DTB)

tmp = tempfile.mkdtemp()
p3 = os.path.join(tmp, "p3.img")
with open(IMG, "rb") as f:
    f.seek(P3_OFF)
    open(p3, "wb").write(f.read(P3_LEN))

env = dict(os.environ, MTOOLS_SKIP_CHECK="1")
r = subprocess.run(["mcopy", "-i", p3, "-o", DTB, "::/rk3562-rg52mini.dtb"],
                   capture_output=True, text=True, env=env)
if r.returncode != 0:
    sys.exit("mcopy: " + r.stderr)

back = os.path.join(tmp, "back.dtb")
with open(back, "wb") as fh:
    fh.write(subprocess.run(["mtype", "-i", p3, "::/rk3562-rg52mini.dtb"],
                            capture_output=True, env=env).stdout)
if open(back, "rb").read() != open(DTB, "rb").read():
    sys.exit("DTB записался неверно")
print("DTB на месте, %d байт, сверен через ФС" % os.path.getsize(back))

r = subprocess.run(["fsck.vfat", "-n", p3], capture_output=True, text=True)
print("fsck.vfat:", r.stdout.strip().splitlines()[-1])
if r.returncode != 0:
    sys.exit("FAT повреждена")

with open(IMG, "r+b") as f:
    f.seek(P3_OFF)
    f.write(open(p3, "rb").read())
    f.flush()
print("образ обновлён")
