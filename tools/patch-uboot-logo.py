#!/usr/bin/env python3
"""Кладёт в загрузочный раздел картинки, которые рисует U-Boot.

Наш загрузчик умеет показывать логотип и анимацию зарядки — но берёт картинки
не из раздела `resource`, как задумано у Rockchip, а из того же FAT-раздела,
где лежит ядро. Файлы кладутся рядом с `Image`:

    logo.bmp            логотип при включении
    battery_0.bmp       кадры анимации зарядки, от пустой батареи
    battery_1.bmp   …
    battery_5.bmp       … до полной
    battery_fail.bmp    неисправность батареи

**`logo_kernel.bmp` класть нельзя.** U-Boot оставляет эту картинку на экране
при передаче управления ядру, и после загрузки экран гаснет. Инструмент
удаляет её из раздела, если она там оказалась.

Формат: BMP 720×1280, 24 бита, повёрнутый на 90° — экран у устройства
портретный, а система разворачивает его на лету (`fbcon=rotate:1`).
Кадры зарядки — 220×110, 8 бит, со сжатием RLE.

Сами файлы в репозитории не лежат: логотип и кадры заводские, сняты
с внутренней памяти устройства. Путь к ним задаётся переменной `LOGO_DIR`.
"""
import subprocess, sys, os

A = "/mnt/t/Dump/RG52Mini/android/"
SRC = os.environ.get("LOGO_DIR", "/mnt/t/Dump/RG52Mini/u-boot/logo/")
IMG = sys.argv[1] if len(sys.argv) > 1 else A + "SyachOS-RG52Mini-V1.0.317m6.0.img"
P3_OFF = 16777216

NEED = ["logo.bmp"] + ["battery_%d.bmp" % i for i in range(6)] + ["battery_fail.bmp"]
FORBID = ["logo_kernel.bmp"]

if not os.path.exists(IMG):
    sys.exit("нет " + IMG)
missing = [n for n in NEED if not os.path.exists(SRC + n)]
if missing:
    sys.exit("нет картинок в %s: %s" % (SRC, ", ".join(missing)))

env = dict(os.environ, MTOOLS_SKIP_CHECK="1")
at = "%s@@%d" % (IMG, P3_OFF)

def run(cmd, must=True):
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if must and r.returncode != 0:
        sys.exit("сбой %s%s%s" % (" ".join(cmd), chr(10), r.stderr))
    return r

listing = run(["mdir", "-i", at, "::/"]).stdout
# mdir печатает число с пробелами между разрядами: «10 160 640 bytes free»
tail = [l for l in listing.splitlines() if "bytes free" in l][0]
free = int("".join(c for c in tail.split("bytes free")[0] if c.isdigit()))
need_bytes = sum(os.path.getsize(SRC + n) for n in NEED)
already = sum(os.path.getsize(SRC + n) for n in NEED if n.lower() in listing.lower())
print("в разделе свободно %d байт, картинки занимают %d" % (free, need_bytes))
if free + already < need_bytes:
    sys.exit("не хватает места: нужно %d, доступно %d" % (need_bytes, free + already))

for n in FORBID:
    if n.lower() in listing.lower():
        run(["mdel", "-i", at, "::/" + n], must=False)
        print("  убрано: %s (из-за неё экран гаснет после загрузки)" % n)

for n in NEED:
    run(["mcopy", "-o", "-i", at, SRC + n, "::/" + n])

# сверка через файловую систему
import tempfile
tmp = tempfile.mkdtemp()
bad = []
for n in NEED:
    dst = os.path.join(tmp, n)
    run(["mcopy", "-o", "-i", at, "::/" + n, dst])
    if open(dst, "rb").read() != open(SRC + n, "rb").read():
        bad.append(n)
if bad:
    sys.exit("записались неверно: " + ", ".join(bad))
print("записано и сверено: %d файлов" % len(NEED))

listing = run(["mdir", "-i", at, "::/"]).stdout
for n in FORBID:
    if n.lower() in listing.lower():
        sys.exit("в разделе осталась %s" % n)
print("logo_kernel.bmp в разделе нет — правильно")

r = subprocess.run(["fsck.vfat", "-n", "-r", IMG], capture_output=True, text=True,
                   input="\n" * 5, env=env)
print("готово")
