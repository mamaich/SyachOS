#!/usr/bin/env python3
"""Puts the quiet aic8800 modules and the spk-mute-delay DTB into the image.

Modules: replaced in the vendor partition via debugfs (rm + write + mode),
then the partition is fsck'd and written back.
DTB: the file grows by 34 bytes but stays within the same FAT cluster count,
so it is replaced with mtools, which keeps the directory consistent.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = A + "SyachOS-RG52Mini-V1.0.317m1.0.img"
P3_OFF, P3_LEN = 16777216, 103809024
P5_OFF, P5_LEN = 1698693120, 267046912
B = A + "bt-payload/"
DTB = A + "rk3562-rg52mini-spkdelay.dtb"

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit("сбой: %s\n%s\n%s" % (" ".join(cmd), r.stdout, r.stderr))
    return r.stdout

tmp = tempfile.mkdtemp()
p5 = os.path.join(tmp, "p5.img")
p3 = os.path.join(tmp, "p3.img")

with open(IMG, "rb") as f:
    f.seek(P5_OFF); open(p5, "wb").write(f.read(P5_LEN))
    f.seek(P3_OFF); open(p3, "wb").write(f.read(P3_LEN))

# ---- модули -------------------------------------------------------------
script = ""
for m in ("aic8800_bsp", "aic8800_fdrv"):
    script += "rm /lib/modules/%s.ko\n" % m
    script += "cd /lib/modules\nwrite %s%s.ko %s.ko\n" % (B, m, m)
    script += "sif /lib/modules/%s.ko mode 0100644\n" % m
script += "quit\n"
subprocess.run(["debugfs", "-w", "-f", "-", p5], input=script,
               capture_output=True, text=True)
run(["e2fsck", "-fp", p5])

for m in ("aic8800_bsp", "aic8800_fdrv"):
    out = os.path.join(tmp, m)
    subprocess.run(["debugfs", "-R", "dump /lib/modules/%s.ko %s" % (m, out), p5],
                   capture_output=True)
    if open(out, "rb").read() != open(B + m + ".ko", "rb").read():
        sys.exit("модуль %s записался неверно" % m)
    print("OK модуль", m)

# ---- DTB ----------------------------------------------------------------
env = dict(os.environ, MTOOLS_SKIP_CHECK="1")
run(["mcopy", "-i", p3, "-o", DTB, "::/rk3562-rg52mini.dtb"], env=env)
back = os.path.join(tmp, "dtb")
with open(back, "wb") as fh:
    r = subprocess.run(["mtype", "-i", p3, "::/rk3562-rg52mini.dtb"],
                       capture_output=True, env=env)
    fh.write(r.stdout)
if open(back, "rb").read() != open(DTB, "rb").read():
    sys.exit("DTB записался неверно")
print("OK dtb")
r = subprocess.run(["fsck.vfat", "-n", p3], capture_output=True, text=True)
print("fsck.vfat:", r.stdout.strip().splitlines()[-1])

# ---- обратно в образ ----------------------------------------------------
with open(IMG, "r+b") as f:
    f.seek(P5_OFF); f.write(open(p5, "rb").read())
    f.seek(P3_OFF); f.write(open(p3, "rb").read())
    f.flush()
print("образ обновлён")
for p in (p5, p3): os.remove(p)
