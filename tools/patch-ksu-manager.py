#!/usr/bin/env python3
"""Кладёт в образ управляющее приложение KernelSU Next.

В ядре есть KernelSU-Next, но одного ядра мало: выдавать root приложениям
некому, пока нет управляющего приложения — оно ведёт список того, кому root
разрешён. Без него `su` есть, а пользоваться им нечему.

## Почему не в /system/app

Ядро опознаёт управляющее приложение **сканированием каталога `/data/app`** и
только его — `KernelSU-Next/kernel/manager/throne_tracker.c`:

    search_manager("/data/app", 2, &uid_list);

Приложение, положенное системным в `/system/app`, туда не попадает: ядро его
не найдёт, приложение запустится, но останется без прав. Поэтому apk лежит в
`/system/etc/rg52` и один раз ставится обычной установкой при первой
загрузке — после неё он оказывается в `/data/app`.

Ставит `/system/bin/ksu_install.sh` по `sys.boot_completed`; раньше нельзя,
`pm` работает только после подъёма `system_server`. Если пакет уже есть,
скрипт ничего не делает — обновлённую руками версию он не трогает.

## Какой apk

Обычный выпуск, не «spoofed»: подделка подписи нужна тем, кто прячет root от
приложений, проверяющих целостность системы, и к работе самого KernelSU
отношения не имеет.

Версия приложения должна совпадать с версией KernelSU в ядре, иначе оно
ругается на несовместимость («Unsupported profile version»). В ядре сейчас
**v3.3.0 (33214)**, приложение берётся той же версии.

    KernelSU_Next_v3.3.0_33214-release.apk   10 209 942 байта

Сам apk в репозитории не лежит: это чужая сборка. Путь задаётся переменной
`KSU_APK`.
"""
import subprocess, sys, os, tempfile, zipfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = sys.argv[1] if len(sys.argv) > 1 else A + "SyachOS-RG52Mini-V1.0.317m6.3.img"
APK = os.environ.get("KSU_APK", A + "KernelSU_Next_v3.3.0_33214-release.apk")
SRC = A + "ksu_install.sh"
P4_OFF, P4_LEN = 121634816, 1577058304
DIR = "/system/etc/rg52"
DST = DIR + "/KernelSUNext.apk"
SH = "/system/bin/ksu_install.sh"
RC = "/system/etc/init/init.perf.rc"
PKG = "com.rifsxd.ksunext"

ADD = """
service ksu_install /system/bin/ksu_install.sh
    user root
    group root system
    oneshot
    disabled

on property:sys.boot_completed=1
    start ksu_install
"""

for p in (APK, SRC, IMG):
    if not os.path.exists(p):
        sys.exit("нет " + p)

# проверка, что это то самое приложение
with zipfile.ZipFile(APK) as z:
    if "AndroidManifest.xml" not in z.namelist():
        sys.exit("это не apk")
    manifest = z.read("AndroidManifest.xml").replace(b"\x00", b"")
if PKG.encode() not in manifest:
    sys.exit("в манифесте нет пакета %s — файл не тот" % PKG)
print("apk: %d байт, пакет %s" % (os.path.getsize(APK), PKG))

tmp = tempfile.mkdtemp()
part = os.path.join(tmp, "p4.img")
with open(IMG, "rb") as f:
    f.seek(P4_OFF)
    open(part, "wb").write(f.read(P4_LEN))

free = subprocess.run(["dumpe2fs", "-h", part], capture_output=True, text=True).stdout
blocks = [l for l in free.splitlines() if "Free blocks" in l]
if blocks:
    n = int(blocks[0].split(":")[1].strip())
    print("в разделе system свободно %d КБ" % (n * 4))
    if n * 4096 < os.path.getsize(APK) * 2:
        sys.exit("мало места в system")

def dump(path, dst):
    subprocess.run(["debugfs", "-R", "dump %s %s" % (path, dst), part],
                   capture_output=True, text=True)
    return open(dst, "rb").read() if os.path.exists(dst) else None

rc_old = dump(RC, os.path.join(tmp, "rc"))
if rc_old is None:
    sys.exit("не нашёл " + RC)
print("init.perf.rc: %d байт" % len(rc_old))

lines = ["mkdir " + DIR, "sif %s mode 040755" % DIR,
         "cd " + DIR, "rm " + DST,
         "write %s KernelSUNext.apk" % APK, "sif %s mode 0100644" % DST,
         "cd /system/bin", "rm " + SH,
         "write %s ksu_install.sh" % SRC, "sif %s mode 0100755" % SH]

if b"ksu_install" in rc_old:
    print("служба уже есть — обновляю только apk и скрипт")
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

if dump(DST, os.path.join(tmp, "b1")) != open(APK, "rb").read():
    sys.exit("apk записался неверно")
if dump(SH, os.path.join(tmp, "b2")) != open(SRC, "rb").read():
    sys.exit("ksu_install.sh записался неверно")
if dump(RC, os.path.join(tmp, "b3")) != rc_new:
    sys.exit("init.perf.rc записался неверно")
print("сверено через ФС: apk, скрипт и служба на месте")

with open(IMG, "r+b") as f:
    f.seek(P4_OFF)
    f.write(open(part, "rb").read())
    f.flush()
print("образ обновлён")
