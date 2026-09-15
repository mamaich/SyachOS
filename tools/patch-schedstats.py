#!/usr/bin/env python3
"""Гасит счётчики планировщика, которые Android включает при загрузке.

/system/etc/init/atrace.rc содержит:

    # Scheduler tracepoints require schedstats=enable
        write /proc/sys/kernel/sched_schedstats 1

Сами по себе счётчики сидят за статическим ключом и ничего не стоят; платим мы
именно за эту строку. Меняем 1 на 0 — один байт, длина файла та же.

`CONFIG_SCHEDSTATS` в ядре намеренно оставлен включённым: когда понадобится
ловить что-нибудь через atrace (так разбирались фризы интерфейса), счётчики
возвращаются одной командой и без пересборки:

    adb shell 'echo 1 > /proc/sys/kernel/sched_schedstats'

Правка делается по месту, прямо в блоке данных файла: inode, права и метка
SELinux остаются нетронутыми — в отличие от перезаписи через debugfs.
"""
import subprocess, sys, re, tempfile, os

IMG = sys.argv[1] if len(sys.argv) > 1 else \
    "/mnt/t/Dump/RG52Mini/android/SyachOS-RG52Mini-V1.0.317m4.0.img"
P4_OFF, P4_LEN = 121634816, 1577058304
PATH = "/system/etc/init/atrace.rc"
OLD = b"write /proc/sys/kernel/sched_schedstats 1"
NEW = b"write /proc/sys/kernel/sched_schedstats 0"
BLK = 4096

tmp = tempfile.mkdtemp()
p4 = os.path.join(tmp, "p4.img")
with open(IMG, "rb") as f:
    f.seek(P4_OFF)
    open(p4, "wb").write(f.read(P4_LEN))

st = subprocess.run(["debugfs", "-R", "stat " + PATH, p4],
                    capture_output=True, text=True).stdout
m = re.search(r"EXTENTS:\s*\n?\(0(?:-\d+)?\):(\d+)", st)
if not m:
    sys.exit("не нашёл блоки файла %s:\n%s" % (PATH, st[-400:]))
block = int(m.group(1))
off = P4_OFF + block * BLK
print("%s: первый блок %d, смещение в образе %d" % (PATH, block, off))

with open(IMG, "r+b") as f:
    f.seek(off)
    data = f.read(BLK)
    if NEW in data:
        print("уже выключено")
        sys.exit(0)
    if data.count(OLD) != 1:
        sys.exit("ожидалось одно вхождение строки, найдено %d" % data.count(OLD))
    f.seek(off)
    f.write(data.replace(OLD, NEW))
    f.flush()
    f.seek(off)
    back = f.read(BLK)

assert NEW in back and OLD not in back, "сверка не сошлась"
print("  было:", OLD.decode())
print("  стало:", NEW.decode())

# сверка через файловую систему: файл должен читаться и содержать новую строку
out = os.path.join(tmp, "check")
with open(IMG, "rb") as f:
    f.seek(P4_OFF)
    open(p4, "wb").write(f.read(P4_LEN))
subprocess.run(["debugfs", "-R", "dump %s %s" % (PATH, out), p4], capture_output=True)
txt = open(out, "rb").read()
assert NEW in txt and OLD not in txt, "через ФС читается старое содержимое"
print("сверено через файловую систему, размер файла %d байт" % len(txt))
