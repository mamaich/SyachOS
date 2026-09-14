#!/usr/bin/env python3
"""Собирает образ с ядром нашей сборки: фильтр ложного babble в USB.

Кладёт в новый образ:
  * /Image на загрузочном разделе — ядро с правкой drivers/usb/dwc3/core.c;
  * /rk3562-rg52mini.dtb — DTB со свойством snps,loa-filter-en-quirk;
  * /lib/modules/*.ko в vendor — модули той же сборки.

Модули обязаны быть из того же прохода сборки: в ядре включён
CONFIG_MODVERSIONS, то есть контрольные суммы символов должны совпадать.

Исходный образ не изменяется: всё пишется в копию.
"""
import subprocess, sys, os, shutil, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
OUT = "/home/mamaich/rg52/out-rg52/"
# Имена можно переопределить окружением: SRC_IMG=... DST_IMG=... — так этим же
# скриптом собирается следующая версия поверх предыдущей.
SRC_IMG = os.environ.get("SRC_IMG", A + "SyachOS-RG52Mini-V1.0.317m2.0.img")
DST_IMG = os.environ.get("DST_IMG", A + "SyachOS-RG52Mini-V1.0.317m3.0.img")
DTB = A + "rk3562-rg52mini-usb.dtb"
P3_OFF, P3_LEN = 16777216, 103809024
P5_OFF, P5_LEN = 1698693120, 267046912
MODULES = ["aic8800_bsp.ko", "aic8800_fdrv.ko", "rk915.ko"]

for f in (SRC_IMG, DTB, OUT + "Image"):
    if not os.path.exists(f):
        sys.exit("нет " + f)

# ядро и модули должны быть одной сборки
ver = subprocess.run(["sh", "-c", "strings %sImage | grep -m1 'Linux version'" % OUT],
                     capture_output=True, text=True).stdout.strip()
print("ядро:", ver.split(" (")[0])
if "loa filter" not in subprocess.run(["sh", "-c", "strings %sImage | grep -c 'loa filter'" % OUT],
                                      capture_output=True, text=True).stdout and \
   subprocess.run(["sh", "-c", "strings %sImage | grep -c 'loa filter'" % OUT],
                  capture_output=True, text=True).stdout.strip() == "0":
    sys.exit("в ядре нет кода фильтра babble — не та сборка")

if not os.path.exists(DST_IMG):
    print("создаю копию образа (4 ГБ, это займёт минуту)...")
    shutil.copyfile(SRC_IMG, DST_IMG)
print("образ:", os.path.basename(DST_IMG), os.path.getsize(DST_IMG), "байт")

tmp = tempfile.mkdtemp()
env = dict(os.environ, MTOOLS_SKIP_CHECK="1")

def part_read(off, ln, name):
    p = os.path.join(tmp, name)
    with open(DST_IMG, "rb") as f:
        f.seek(off)
        open(p, "wb").write(f.read(ln))
    return p

def part_write(off, p):
    with open(DST_IMG, "r+b") as f:
        f.seek(off)
        f.write(open(p, "rb").read())
        f.flush()

# --- загрузочный раздел: ядро и DTB
p3 = part_read(P3_OFF, P3_LEN, "p3.img")
for src, dst in ((OUT + "Image", "::/Image"), (DTB, "::/rk3562-rg52mini.dtb")):
    r = subprocess.run(["mcopy", "-i", p3, "-o", src, dst],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.exit("mcopy %s: %s" % (dst, r.stderr))
    back = os.path.join(tmp, "back")
    open(back, "wb").write(subprocess.run(["mtype", "-i", p3, dst],
                                          capture_output=True, env=env).stdout)
    if open(back, "rb").read() != open(src, "rb").read():
        sys.exit("%s записался неверно" % dst)
    print("  %-28s %9d байт, сверен через ФС" % (dst, os.path.getsize(src)))

r = subprocess.run(["fsck.vfat", "-n", p3], capture_output=True, text=True)
print("fsck.vfat:", r.stdout.strip().splitlines()[-1])
if r.returncode != 0:
    sys.exit("FAT повреждена")
part_write(P3_OFF, p3)

# --- vendor: модули
p5 = part_read(P5_OFF, P5_LEN, "p5.img")
lines = ["cd /lib/modules"]
present = []
for m in MODULES:
    src = OUT + m
    if not os.path.exists(src):
        print("  %-28s пропущен, нет в сборке" % m)
        continue
    chk = subprocess.run(["debugfs", "-R", "stat /lib/modules/" + m, p5],
                         capture_output=True, text=True)
    if "File not found" in chk.stderr or "File not found" in chk.stdout:
        print("  %-28s пропущен, в образе такого нет" % m)
        continue
    lines += ["rm /lib/modules/" + m, "write %s %s" % (src, m),
              "sif /lib/modules/%s mode 0100644" % m]
    present.append(m)
lines.append("quit")
subprocess.run(["debugfs", "-w", "-f", "-", p5], input="\n".join(lines) + "\n",
               capture_output=True, text=True)

r = subprocess.run(["e2fsck", "-fp", p5], capture_output=True, text=True)
print("e2fsck vendor:", r.stdout.strip().splitlines()[-1])
if r.returncode not in (0, 1):
    sys.exit("e2fsck недоволен")

for m in present:
    back = os.path.join(tmp, "back_" + m)
    subprocess.run(["debugfs", "-R", "dump /lib/modules/%s %s" % (m, back), p5],
                   capture_output=True)
    if open(back, "rb").read() != open(OUT + m, "rb").read():
        sys.exit("%s записался неверно" % m)
    print("  %-28s %9d байт, сверен через ФС" % (m, os.path.getsize(OUT + m)))
part_write(P5_OFF, p5)
print("образ готов")
