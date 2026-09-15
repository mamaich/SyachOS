#!/usr/bin/env python3
"""Снимает запрет на показ логотипа при загрузке: loglevel=4 -> 5.

Тонкость, которую не угадать. `fbcon` отказывается рисовать логотип, если
консоль переведена в тихий режим — drivers/video/fbdev/core/fbcon.c:

    if (logo_shown < 0 && console_loglevel <= CONSOLE_LOGLEVEL_QUIET)
        logo_shown = FBCON_LOGO_DONTSHOW;

`CONSOLE_LOGLEVEL_QUIET` в этом ядре равен 4, а в загрузочной строке с версии
m1.0 стоял ровно `loglevel=4` — чтобы экран не заливало сообщениями. Условие
«меньше или равно» выполнялось, и ядро само гасило логотип.

Поднимаем на единицу. Текста на экране от этого не прибавится: экранной
консоли в этой прошивке нет вовсе (в `/proc/consoles` только `ttyFIQ0` и
`ramoops`), поэтому сообщения уходят в порт, а на экране остаётся логотип.

Разбор: docs/11-boot-logo.md

Правка ровно в один символ, длина файла не меняется.
"""
import sys

IMG = sys.argv[1] if len(sys.argv) > 1 else \
    "/mnt/t/Dump/RG52Mini/android/SyachOS-RG52Mini-V1.0.317m5.0.img"
P3_OFF, P3_LEN = 16777216, 103809024
OLD, NEW = b"loglevel=4", b"loglevel=5"

with open(IMG, "r+b") as f:
    f.seek(P3_OFF)
    blob = f.read(P3_LEN)

    at = blob.find(b"DEFAULT Android13")
    if at < 0:
        sys.exit("не нашёл extlinux.conf в загрузочном разделе")
    end = blob.find(b"androidboot.selinux=permissive", at)
    if end < 0:
        sys.exit("не нашёл конец строки APPEND")
    end += len(b"androidboot.selinux=permissive")
    conf = blob[at:end]

    if NEW in conf:
        print("уже loglevel=5")
        sys.exit(0)
    if conf.count(OLD) != 1:
        sys.exit("ожидалось одно вхождение loglevel=4, найдено %d" % conf.count(OLD))

    pos = at + conf.find(OLD)
    f.seek(P3_OFF + pos)
    f.write(NEW)
    f.flush()
    f.seek(P3_OFF + pos)
    back = f.read(len(NEW))

assert back == NEW, "сверка не сошлась"
print("loglevel=4 -> loglevel=5 (смещение в образе %d)" % (P3_OFF + pos))
