#!/usr/bin/env python3
"""Кладёт в образ загрузчик первой ступени (SPL), снятый с eMMC.

Зачем: в образе SyachOS область `idbloader` (сектор 64) **пуста** — карта не
была загрузочной сама по себе, её поднимал SPL с eMMC. Разбор:
docs/12-bootloader.md

**FIT-образ U-Boot по умолчанию НЕ трогается, и это важно.** В нём лежат не
только U-Boot, но и ATF с OP-TEE. Версия с eMMC (10.07.2026) ломает выключение
устройства: по команде «выключить» PMIC делает сброс вместо снятия питания, и
устройство включается обратно. Проверено разделением: с авторским FIT
выключение работает, с новым — нет, при том же ядре и том же SPL.
Различие видно и по регистрам PMIC:

    удачное выключение, включение кнопкой:  ON_SOURCE=0x80  OFF_SOURCE=0x08
    «выключил, а оно вернулось»:            ON_SOURCE=0x10  OFF_SOURCE=0x80

Поэтому берём только SPL — он чинит зависание при включении с воткнутым USB, —
а FIT оставляем авторский.

Записать и FIT тоже (для опытов) можно так:

    WITH_UBOOT=1 python3 tools/patch-bootloader.py образ.img

Двоичные файлы в репозитории не лежат: это загрузчик производителя. Снимается
со своего устройства (нужен root):

    adb shell dd if=/dev/block/mmcblk0 of=/data/local/tmp/idbloader.bin \\
              bs=512 skip=64 count=16320
    adb pull /data/local/tmp/idbloader.bin ~/rg52/bootloader/

Таблица разделов (сектора 0..63) не трогается — иначе образ перестанет быть
образом.
"""
import sys, os, re

A = "/mnt/t/Dump/RG52Mini/android/"
SRC = os.environ.get("BOOTLOADER", "/home/mamaich/rg52/bootloader/")
IMG = sys.argv[1] if len(sys.argv) > 1 else A + "SyachOS-RG52Mini-V1.0.317m5.0.img"
WITH_UBOOT = os.environ.get("WITH_UBOOT", "") not in ("", "0", "no")

# смещения из GPT образа, в секторах по 512 байт
IDB_LBA, IDB_MAX = 64, 16320        # до начала раздела uboot на 16384
UBOOT_LBA, UBOOT_MAX = 16384, 8192  # ровно раздел uboot, 4 МБ

PARTS = [("idbloader.bin", IDB_LBA, IDB_MAX)]
if WITH_UBOOT:
    PARTS.append(("uboot.bin", UBOOT_LBA, UBOOT_MAX))
    print("!! пишу и FIT тоже — помните про сломанное выключение")

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
              % (name, lba, len(data), "сверен" if ok else "ЗАПИСАЛСЯ НЕВЕРНО"))
        if not ok:
            sys.exit(1)

    # какой U-Boot остался в образе — видно по строке версии внутри FIT
    f.seek(UBOOT_LBA * 512)
    blob = f.read(UBOOT_MAX * 512)

m = re.findall(rb"U-Boot 2[0-9]{3}\.[0-9]{2}[^)]*\)", blob)
if m:
    print("  U-Boot в образе:", m[-1].decode("ascii", "replace"))
print("готово")
