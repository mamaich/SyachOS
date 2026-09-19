#!/usr/bin/env python3
"""Убирает превращение выключения в перезагрузку: reboot_on_failure у vold.

Симптом: «Выключить» из меню приводит к перезагрузке. Долгое удержание кнопки
питания выключает нормально — то есть аппаратная часть цела.

В /system/etc/init/vold.rc у службы стоит:

    shutdown critical
    reboot_on_failure reboot,vold-failed

При выключении init останавливает службы, завершение vold считает сбоем и,
по этой строке, подменяет цель выключения на перезагрузку. В журнале прошлой
загрузки (/sys/fs/pstore/console-ramoops-0) это видно дословно:

    init: Service vold has 'reboot_on_failure' option and failed, shutting down system.
    ...через 5,6 с...
    init: Reboot ending, jumping to kernel

Ни «System power off», ни «Power off failed !» из drivers/mfd/rk808.c в
журнале нет — до ядра команда выключения не доходит вовсе.

Смысл строки — перезагрузить устройство, если vold не смог запуститься на
старте (иначе не поднимется /data). Но на выключении она вредна, а сама
проверка при запуске остаётся: init и без неё не пустит систему дальше.

Правка: строка `reboot_on_failure` убирается, `shutdown critical` остаётся.

Это не лечит вторую, независимую беду — когда плата включается обратно уже
после честного снятия питания (см. docs/12-bootloader.md). Проверять надо
раздельно: выключение из меню лечится здесь, самопроизвольное включение —
в загрузчике.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = sys.argv[1] if len(sys.argv) > 1 else A + "SyachOS-RG52Mini-V1.0.317m5.0.img"
P4_OFF, P4_LEN = 121634816, 1577058304
RC = "/system/etc/init/vold.rc"
DROP = b"    reboot_on_failure reboot,vold-failed\n"

if not os.path.exists(IMG):
    sys.exit("нет " + IMG)

tmp = tempfile.mkdtemp()
part = os.path.join(tmp, "p4.img")
with open(IMG, "rb") as f:
    f.seek(P4_OFF)
    open(part, "wb").write(f.read(P4_LEN))

def dump(path, dst):
    r = subprocess.run(["debugfs", "-R", "dump %s %s" % (path, dst), part],
                       capture_output=True, text=True)
    if not os.path.exists(dst):
        sys.exit("не смог достать %s: %s" % (path, r.stderr))
    return open(dst, "rb").read()

old = dump(RC, os.path.join(tmp, "rc"))
print("vold.rc: %d байт" % len(old))

if b"service vold" not in old:
    sys.exit("не похоже на vold.rc")
if DROP not in old:
    if b"reboot_on_failure" in old:
        sys.exit("строка есть, но записана иначе — правка отменена")
    print("правка не нужна: reboot_on_failure уже убран")
    sys.exit(0)
if old.count(DROP) != 1:
    sys.exit("ожидалась одна строка reboot_on_failure, найдено %d" % old.count(DROP))

new = old.replace(DROP, b"", 1)
assert b"shutdown critical" in new, "потеряна строка shutdown critical"
print("убрано: %s" % DROP.decode().strip())

new_path = os.path.join(tmp, "vold.rc")
open(new_path, "wb").write(new)

script = "\n".join(["rm " + RC, "cd /system/etc/init",
                    "write %s vold.rc" % new_path,
                    "sif %s mode 0100644" % RC, "quit"]) + "\n"
subprocess.run(["debugfs", "-w", "-f", "-", part], input=script,
               capture_output=True, text=True)

r = subprocess.run(["e2fsck", "-fp", part], capture_output=True, text=True)
print("e2fsck:", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "чисто")
if r.returncode not in (0, 1):
    sys.exit("e2fsck недоволен")

back = dump(RC, os.path.join(tmp, "back"))
if back != new:
    sys.exit("vold.rc записался неверно")
print("сверено через ФС: %d байт, reboot_on_failure отсутствует" % len(back))

with open(IMG, "r+b") as f:
    f.seek(P4_OFF)
    f.write(open(part, "rb").read())
    f.flush()
print("образ обновлён")
