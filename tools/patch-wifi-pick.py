#!/usr/bin/env python3
"""Загружает драйвер Wi-Fi по факту железа: RK915 или AIC8800, но не оба.

## Зачем

Плата ревизии A несёт **RK915**, ревизии B — **AIC8800D80**. Чипы сидят на
одном слоте SDIO (`mmc@ff890000`) и делят один вывод питания
(`wifi-poweren`, GPIO0_A6). Управляют им оба драйвера через общие функции
ядра `rockchip_wifi_power()` и `rockchip_wifi_set_carddetect()` — то есть
любой может обесточить чужой чип:

    rk915/src/platform.c:16,18,23   rockchip_wifi_power(0/1/0)
    aic8800_bsp/aicsdio.c:567,569   rockchip_wifi_power(0/1)
    aic8800_bsp/aicsdio.c:642       rockchip_wifi_power(0)   при неудаче

Пока оба драйвера грузились подряд из `init.insmod.cfg`, на ревизии A
получалось так: `rk915` находил свой чип и поднимал Wi-Fi, а следом
`aic8800_bsp` снимал общее питание, своего чипа не находил и оставлял линию
обесточенной. Рабочий Wi-Fi выбивало. На ревизии B этого не видно: там
`rk915` уходит первым и освобождает линию для AIC8800.

## Как чиним

Две строки `insmod aic8800_*` убираются из `init.insmod.cfg`, а вместо них
появляется служба: когда ядро закончило загрузку модулей
(`vendor.all.modules.ready=1`), скрипт смотрит, появился ли интерфейс
`wlan*`. Появился — значит, RK915 нашёл свой чип, и трогать ничего нельзя.
Не появился — чип наш, догружаем AIC8800.

Так один образ остаётся годным для обеих плат.

Цена — несколько секунд ожидания на ревизии B: столько скрипт даёт RK915
на то, чтобы объявиться. Wi-Fi поднимается задолго до того, как система
до него доберётся, так что заметить это нельзя.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = sys.argv[1] if len(sys.argv) > 1 else A + "SyachOS-RG52Mini-V1.0.317m6.1.img"
P5_OFF, P5_LEN = 1698693120, 267046912
CFG = "/etc/init.insmod.cfg"
SH = "/bin/wifi_pick.sh"
RC = "/etc/init/rg52-wifi.rc"

SCRIPT = """#!/vendor/bin/sh
# Плата ревизии A несёт RK915, ревизии B — AIC8800D80. Чипы сидят на одном
# слоте SDIO и делят вывод питания, поэтому загружать оба драйвера подряд
# нельзя: тот, что грузится вторым, снимает питание и выбивает первый.
#
# rk915 грузится раньше, из init.insmod.cfg. Если он нашёл свой чип, интерфейс
# уже есть — AIC8800 не трогаем. Если за отведённое время не появился, значит
# чип наш, догружаем.
i=0
while [ $i -lt 20 ]; do
    for n in /sys/class/net/wlan*; do
        if [ -e "$n" ]; then
            log -t wifi_pick "RK915 поднял $n, AIC8800 не нужен"
            exit 0
        fi
    done
    i=$((i + 1))
    sleep 0.2
done

log -t wifi_pick "интерфейса нет, гружу AIC8800"
insmod /vendor/lib/modules/aic8800_bsp.ko
insmod /vendor/lib/modules/aic8800_fdrv.ko
"""

RC_TEXT = """# Выбор драйвера Wi-Fi по факту железа, см. tools/patch-wifi-pick.py
service rg52_wifi_pick /vendor/bin/wifi_pick.sh
    user root
    group root wifi inet
    oneshot
    disabled

on property:vendor.all.modules.ready=1
    start rg52_wifi_pick
"""

if not os.path.exists(IMG):
    sys.exit("нет " + IMG)

tmp = tempfile.mkdtemp()
part = os.path.join(tmp, "p5.img")
with open(IMG, "rb") as f:
    f.seek(P5_OFF)
    open(part, "wb").write(f.read(P5_LEN))

def dump(path, dst):
    subprocess.run(["debugfs", "-R", "dump %s %s" % (path, dst), part],
                   capture_output=True, text=True)
    return open(dst, "rb").read() if os.path.exists(dst) else None

cfg = dump(CFG, os.path.join(tmp, "cfg"))
if cfg is None or b"insmod" not in cfg:
    sys.exit("не нашёл %s" % CFG)

lines = cfg.decode().split("\n")
out, off = [], 0
for l in lines:
    if l.startswith("insmod /vendor/lib/modules/aic8800"):
        out.append("#" + l)
        off += 1
    else:
        out.append(l)
if off == 0 and "#insmod /vendor/lib/modules/aic8800" in cfg.decode():
    print("строки aic8800 уже отключены")
elif off != 2:
    sys.exit("ожидалось две строки insmod aic8800, найдено %d" % off)
else:
    print("убрано из init.insmod.cfg: %d строки insmod aic8800" % off)
new_cfg = "\n".join(out)

if "insmod /vendor/lib/modules/rk915.ko" not in new_cfg:
    sys.exit("в init.insmod.cfg нет строки rk915 — образ не тот, что ожидался")

p_cfg = os.path.join(tmp, "cfg.new"); open(p_cfg, "w").write(new_cfg)
p_sh = os.path.join(tmp, "wifi_pick.sh"); open(p_sh, "w").write(SCRIPT)
p_rc = os.path.join(tmp, "rg52-wifi.rc"); open(p_rc, "w").write(RC_TEXT)

script = "\n".join([
    "rm " + CFG, "cd /etc", "write %s init.insmod.cfg" % p_cfg,
    "sif %s mode 0100644" % CFG,
    "rm " + SH, "cd /bin", "write %s wifi_pick.sh" % p_sh,
    "sif %s mode 0100755" % SH,
    "rm " + RC, "cd /etc/init", "write %s rg52-wifi.rc" % p_rc,
    "sif %s mode 0100644" % RC,
    "quit"]) + "\n"
subprocess.run(["debugfs", "-w", "-f", "-", part], input=script,
               capture_output=True, text=True)

r = subprocess.run(["e2fsck", "-fp", part], capture_output=True, text=True)
print("e2fsck:", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "чисто")
if r.returncode not in (0, 1):
    sys.exit("e2fsck недоволен")

back_cfg = dump(CFG, os.path.join(tmp, "b1"))
back_sh = dump(SH, os.path.join(tmp, "b2"))
back_rc = dump(RC, os.path.join(tmp, "b3"))
if back_cfg.decode() != new_cfg:
    sys.exit("init.insmod.cfg записался неверно")
if back_sh.decode() != SCRIPT:
    sys.exit("wifi_pick.sh записался неверно")
if back_rc.decode() != RC_TEXT:
    sys.exit("rg52-wifi.rc записался неверно")
print("сверено через ФС: три файла")
print("  в init.insmod.cfg осталось строк insmod:",
      sum(1 for l in back_cfg.decode().split("\n") if l.startswith("insmod")))

with open(IMG, "r+b") as f:
    f.seek(P5_OFF)
    f.write(open(part, "rb").read())
    f.flush()
print("образ обновлён")
