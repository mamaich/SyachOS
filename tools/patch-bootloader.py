#!/usr/bin/env python3
"""Кладёт в образ загрузчик первой ступени и U-Boot, снятые с eMMC.

Зачем: в образе SyachOS область `idbloader` (сектор 64) **пуста** — карта не
была загрузочной сама по себе, её поднимал SPL с eMMC, а U-Boot в разделе
`uboot` был старше того, что стоит на eMMC:

    карта:  U-Boot 2017.09 от 04.11.2025, SPL нет
    eMMC:   U-Boot 2017.09 от 10.07.2026, SPL от 10.06.2026

Со старым загрузчиком устройство не грузилось, если в момент включения был
воткнут USB-кабель; с новым эта беда пропала. Разбор: docs/12-bootloader.md

Двоичные файлы в репозитории не лежат намеренно: это загрузчик производителя.
Снять со своего устройства (нужен root):

    adb shell dd if=/dev/block/mmcblk0 of=/data/local/tmp/idbloader.bin \\
              bs=512 skip=64 count=16320
    adb shell dd if=/dev/block/mmcblk0 of=/data/local/tmp/uboot.bin \\
              bs=512 skip=16384 count=8192
    adb pull /data/local/tmp/idbloader.bin ~/rg52/bootloader/
    adb pull /data/local/tmp/uboot.bin ~/rg52/bootloader/

Таблица разделов (сектора 0..63) не трогается — иначе образ перестанет быть
образом. Раздел `trust` не нужен: ATF и OP-TEE лежат внутри FIT-образа U-Boot.
"""
import sys, os, hashlib

A = "/mnt/t/Dump/RG52Mini/android/"
SRC = os.environ.get("BOOTLOADER", "/home/mamaich/rg52/bootloader/")
IMG = sys.argv[1] if len(sys.argv) > 1 else A + "SyachOS-RG52Mini-V1.0.317m5.0.img"

# смещения из GPT образа, в секторах по 512 байт
IDB_LBA, IDB_MAX = 64, 16320        # до начала раздела uboot на 16384
UBOOT_LBA, UBOOT_MAX = 16384, 8192  # ровно раздел uboot, 4 МБ

PARTS = [("idbloader.bin", IDB_LBA, IDB_MAX),
         ("uboot.bin", UBOOT_LBA, UBOOT_MAX)]

for name, _, _ in PARTS:
    if not os.path.exists(SRC + name):
        sys.exit("нет %s%s — снимите загрузчик с устройства, см. заголовок файла"
                 % (SRC, name))
if not os.path.exists(IMG):
    sys.exit("нет " + IMG)

print("образ:", os.path.basename(IMG))
with open(IMG, "r+b") as f:
    for name, lba, maxblk in PARTS:
        data = open(SRC + name, "rb").read()
        if len(data) > maxblk * 512:
            sys.exit("%s не влезает: %d байт при пределе %d"
                     % (name, len(data), maxblk * 512))
        f.seek(lba * 512)
        f.write(data)
        f.flush()
        f.seek(lba * 512)
        back = f.read(len(data))
        ok = back == data
        print("  %-16s сектор %6d  %8d байт  %s"
              % (name, lba, len(data),
                 "сверен" if ok else "ЗАПИСАЛСЯ НЕВЕРНО"))
        if not ok:
            sys.exit(1)

    # версия U-Boot видна строкой внутри образа — заодно подтверждаем, какой лёг
    f.seek(UBOOT_LBA * 512)
    blob = f.read(UBOOT_MAX * 512)
import re
m = re.findall(rb"U-Boot 20[0-9.]+[^\x00]{0,60}", blob)
if m:
    print("  версия:", m[-1].decode("ascii", "replace"))
print("готово")
