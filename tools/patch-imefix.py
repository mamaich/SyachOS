#!/usr/bin/env python3
"""Удерживает выбранную клавиатуру после перезагрузки.

Система при каждой загрузке возвращает `default_input_method` на штатную
`com.android.inputmethod.leanback`. Список включённых методов при этом
сохраняется — слетает только выбор по умолчанию, и сторонняя клавиатура
живёт ровно до первой перезагрузки.

Кладёт `/system/bin/ime_fix.sh` и дописывает службу в
`/system/etc/init/init.perf.rc`, запускающую его по `sys.boot_completed`.
Раньше нельзя: `ime` и `settings` работают только после подъёма
`system_server`.

Скрипт ничего не навязывает силой — он читает имя клавиатуры из свойства
и проверяет, установлена ли она:

    setprop persist.rg52.ime com.liskovsoft.leankeyboard/.ime.LeanbackImeService

Умолчание в скрипте — LeanKey, потому что она лежит в образе
(`tools/patch-leankey.py`). Если её удалить, скрипт молча ничего не сделает.

Служба дописывается один раз, сам скрипт перезаписывается при каждом
запуске — так правку можно обновлять на уже собранном образе.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = sys.argv[1] if len(sys.argv) > 1 else A + "SyachOS-RG52Mini-V1.0.317m6.3.img"
SRC = A + "ime_fix.sh"
P4_OFF, P4_LEN = 121634816, 1577058304
RC = "/system/etc/init/init.perf.rc"
SH = "/system/bin/ime_fix.sh"

ADD = """
service ime_fix /system/bin/ime_fix.sh
    user root
    group root system
    oneshot
    disabled

on property:sys.boot_completed=1
    start ime_fix
"""

if not os.path.exists(SRC):
    sys.exit("нет " + SRC)
if not os.path.exists(IMG):
    sys.exit("нет " + IMG)

tmp = tempfile.mkdtemp()
part = os.path.join(tmp, "p4.img")
with open(IMG, "rb") as f:
    f.seek(P4_OFF)
    open(part, "wb").write(f.read(P4_LEN))

def dump(path, dst):
    subprocess.run(["debugfs", "-R", "dump %s %s" % (path, dst), part],
                   capture_output=True, text=True)
    return open(dst, "rb").read() if os.path.exists(dst) else None

rc_old = dump(RC, os.path.join(tmp, "rc"))
if rc_old is None:
    sys.exit("не нашёл " + RC)
print("init.perf.rc: %d байт" % len(rc_old))

lines = ["cd /system/bin", "rm " + SH, "write %s ime_fix.sh" % SRC,
         "sif %s mode 0100755" % SH]
if b"ime_fix" in rc_old:
    print("служба уже есть — обновляю только скрипт")
    rc_new = rc_old
else:
    rc_new = rc_old.rstrip(b"\n") + b"\n" + ADD.encode()
    rc_path = os.path.join(tmp, "rc.new")
    open(rc_path, "wb").write(rc_new)
    lines += ["rm " + RC, "cd /system/etc/init",
              "write %s init.perf.rc" % rc_path, "sif %s mode 0100644" % RC]
lines.append("quit")

subprocess.run(["debugfs", "-w", "-f", "-", part], input="\n".join(lines) + "\n",
               capture_output=True, text=True)

r = subprocess.run(["e2fsck", "-fp", part], capture_output=True, text=True)
print("e2fsck:", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "чисто")
if r.returncode not in (0, 1):
    sys.exit("e2fsck недоволен")

back_sh = dump(SH, os.path.join(tmp, "b1"))
back_rc = dump(RC, os.path.join(tmp, "b2"))
if back_sh != open(SRC, "rb").read():
    sys.exit("ime_fix.sh записался неверно")
if back_rc != rc_new:
    sys.exit("init.perf.rc записался неверно")
print("сверено через ФС: ime_fix.sh %d байт, служба на месте" % len(back_sh))

with open(IMG, "r+b") as f:
    f.seek(P4_OFF)
    f.write(open(part, "rb").read())
    f.flush()
print("образ обновлён")
