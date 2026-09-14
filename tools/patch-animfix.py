#!/usr/bin/env python3
"""Убирает четырёхсекундные фризы интерфейса: animator_duration_scale = 0.

Кладёт в /system/bin/anim_fix.sh и добавляет в /system/etc/init/init.perf.rc
службу, запускающую его по sys.boot_completed. Раньше нельзя: settings
работает только когда поднялся system_server, а служба perf_apply автора
стартует «on boot», то есть до этого.

Службу дописываем один раз, а сам скрипт перезаписываем при каждом запуске —
так правку можно обновлять на уже пропатченном образе.

Почему это лечит — см. комментарий в самом anim_fix.sh.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = A + "SyachOS-RG52Mini-V1.0.317-aic8800-wifi-bt.img"
SRC = A + "anim_fix.sh"
P4_OFF, P4_LEN = 121634816, 1577058304
RC = "/system/etc/init/init.perf.rc"
SH = "/system/bin/anim_fix.sh"

ADD = """
service anim_fix /system/bin/anim_fix.sh
    user root
    group root system
    oneshot
    disabled

on property:sys.boot_completed=1
    start anim_fix
"""

if not os.path.exists(SRC):
    sys.exit("нет " + SRC)

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

rc_old = dump(RC, os.path.join(tmp, "rc"))
print("init.perf.rc: %d байт" % len(rc_old))
if b"perf_apply" not in rc_old:
    sys.exit("не похоже на init.perf.rc автора")

lines = ["cd /system/bin", "rm " + SH, "write %s anim_fix.sh" % SRC,
         "sif %s mode 0100755" % SH]
if b"anim_fix" in rc_old:
    print("служба в init.perf.rc уже есть — обновляю только скрипт")
    rc_new = rc_old
else:
    rc_new = rc_old.rstrip(b"\n") + b"\n" + ADD.encode()
    rc_path = os.path.join(tmp, "rc.new")
    open(rc_path, "wb").write(rc_new)
    lines += ["rm " + RC, "cd /system/etc/init",
              "write %s init.perf.rc" % rc_path, "sif %s mode 0100644" % RC]
lines.append("quit")
script = "\n".join(lines) + "\n"

subprocess.run(["debugfs", "-w", "-f", "-", part], input=script,
               capture_output=True, text=True)

r = subprocess.run(["e2fsck", "-fp", part], capture_output=True, text=True)
print("e2fsck:", r.stdout.strip().splitlines()[-1])
if r.returncode not in (0, 1):
    sys.exit("e2fsck недоволен")

back_rc = dump(RC, os.path.join(tmp, "back_rc"))
back_sh = dump(SH, os.path.join(tmp, "back_sh"))
if back_rc != rc_new:
    sys.exit("init.perf.rc записался неверно")
if back_sh != open(SRC, "rb").read():
    sys.exit("anim_fix.sh записался неверно")
print("сверено через ФС: init.perf.rc %d байт, anim_fix.sh %d байт"
      % (len(back_rc), len(back_sh)))
if b"while" in back_sh and b"24" in back_sh:
    print("в скрипте есть удержание значения (цикл на две минуты)")

with open(IMG, "r+b") as f:
    f.seek(P4_OFF)
    f.write(open(part, "rb").read())
    f.flush()
print("образ обновлён")
