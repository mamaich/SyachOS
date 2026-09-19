#!/usr/bin/env python3
"""Кладёт в образ загрузчик: первую ступень с eMMC и, если задан, наш FIT.

## Первая ступень (SPL, сектор 64)

В образе SyachOS эта область **пуста** — карта не была загрузочной сама по
себе, её поднимал SPL с внутренней памяти. Берём его оттуда:

    adb shell dd if=/dev/block/mmcblk0 of=/data/local/tmp/idbloader.bin \\
              bs=512 skip=64 count=16320
    adb pull /data/local/tmp/idbloader.bin ~/rg52/bootloader/

В репозитории двоичного файла нет: это загрузчик производителя.

## Вторая ступень (FIT, сектор 16384)

Здесь лежат U-Boot, ATF и OP-TEE одним образом. Мы собираем **свой**
(форк `u-boot-rk3562-rg52mini`), в нём работают выключение, режим зарядки
с выходом по длинному нажатию, логотип и консоль на выведенных наружу
площадках. Путь к готовому образу задаётся переменной:

    UBOOT_FIT=~/rg52/u-boot/build/uboot.img python3 tools/patch-bootloader.py образ.img

Без этой переменной раздел не трогается — в образе остаётся тот FIT, что был.

**Заводской FIT с внутренней памяти брать нельзя.** Он лечит зависание при
включении с кабелем, но ломает выключение: из его дерева срезано
`interrupt-parent`, PMIC остаётся без прерывания, и команда выключения
оборачивается сбросом. Разбор: docs/12-bootloader.md

К FIT прилагается то, что он читает с загрузочного раздела: дерево ядра под
именем `rk3562-rg52mini.dtb`, `logo.bmp` и кадры зарядки. Их кладёт
`tools/patch-uboot-logo.py`.

Таблица разделов (сектора 0..63) не трогается — иначе образ перестанет быть
образом.
"""
import sys, os, re

A = "/mnt/t/Dump/RG52Mini/android/"
SRC = os.environ.get("BOOTLOADER", "/home/mamaich/rg52/bootloader/")
FIT = os.environ.get("UBOOT_FIT", "")
IMG = sys.argv[1] if len(sys.argv) > 1 else A + "SyachOS-RG52Mini-V1.0.317m6.0.img"

# смещения из GPT образа, в секторах по 512 байт
IDB_LBA, IDB_MAX = 64, 16320        # до начала раздела uboot на 16384
UBOOT_LBA, UBOOT_MAX = 16384, 8192  # ровно раздел uboot, 4 МБ

PARTS = [(SRC + "idbloader.bin", "первая ступень", IDB_LBA, IDB_MAX)]
if FIT:
    PARTS.append((os.path.expanduser(FIT), "наш FIT", UBOOT_LBA, UBOOT_MAX))

for path, name, _, _ in PARTS:
    if not os.path.exists(path):
        sys.exit("нет %s (%s) — см. заголовок файла" % (path, name))
if not os.path.exists(IMG):
    sys.exit("нет " + IMG)

print("образ:", os.path.basename(IMG))
with open(IMG, "r+b") as f:
    for path, name, lba, maxblk in PARTS:
        data = open(path, "rb").read()
        if len(data) > maxblk * 512:
            sys.exit("%s не влезает: %d байт при пределе %d"
                     % (name, len(data), maxblk * 512))
        f.seek(lba * 512)
        f.write(data)
        f.flush()
        f.seek(lba * 512)
        ok = f.read(len(data)) == data
        print("  %-16s сектор %6d  %8d байт  %s"
              % (name, lba, len(data), "сверено" if ok else "ЗАПИСАЛСЯ НЕВЕРНО"))
        if not ok:
            sys.exit(1)

    f.seek(UBOOT_LBA * 512)
    blob = f.read(UBOOT_MAX * 512)

# какой загрузчик остался в образе: наш опознаётся по модели в своём дереве
if b"AISLPC RG52 Mini" in blob:
    print("  в образе наш загрузчик (дерево AISLPC RG52 Mini)")
else:
    m = re.findall(rb"U-Boot 2[0-9]{3}\.[0-9]{2}[^)]*\)", blob)
    print("  в образе чужой загрузчик:",
          m[-1].decode("ascii", "replace") if m else "версия не опознана")
print("готово")
