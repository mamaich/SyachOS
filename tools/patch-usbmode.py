#!/usr/bin/env python3
"""Кладёт утилиту usbmode в /system/bin образа.

Определение роли USB работает само (см. patch-typec.py), утилита нужна для
одного случая: если внешнее питание воткнули в уже подключённый хаб, роли
по правилам Type-C остаются прежними и консоль кормит хаб. Тогда
`usbmode sink` запрашивает смену роли питания.

Плюс принудительные режимы usb2-phy на случай периферии, которая
неправильно тянет линии CC.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = A + "SyachOS-RG52Mini-V1.0.317-aic8800-wifi-bt.img"
SRC = A + "usbmode"
P4_OFF, P4_LEN = 121634816, 1577058304
DST = "/system/bin/usbmode"

if not os.path.exists(SRC):
    sys.exit("нет " + SRC)
head = open(SRC, "rb").read(20)
if not head.startswith(b"#!/system/bin/sh"):
    sys.exit("не похоже на скрипт для Android")

tmp = tempfile.mkdtemp()
part = os.path.join(tmp, "p4.img")
with open(IMG, "rb") as f:
    f.seek(P4_OFF)
    open(part, "wb").write(f.read(P4_LEN))

script = ("cd /system/bin\nwrite %s usbmode\nsif %s mode 0100755\nquit\n" % (SRC, DST))
subprocess.run(["debugfs", "-w", "-f", "-", part], input=script,
               capture_output=True, text=True)
r = subprocess.run(["e2fsck", "-fp", part], capture_output=True, text=True)
print("e2fsck:", r.stdout.strip().splitlines()[-1])

back = os.path.join(tmp, "back")
subprocess.run(["debugfs", "-R", "dump %s %s" % (DST, back), part], capture_output=True)
if open(back, "rb").read() != open(SRC, "rb").read():
    sys.exit("записалось неверно")
print("usbmode на месте, %d байт, сверен через ФС" % os.path.getsize(back))

with open(IMG, "r+b") as f:
    f.seek(P4_OFF)
    f.write(open(part, "rb").read())
    f.flush()
print("образ обновлён")
