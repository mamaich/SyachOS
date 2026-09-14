#!/usr/bin/env python3
"""Добавляет в DTB образа наши свойства: фильтр babble в USB и защиту от перегрева.

Плохой кабель или статика могут подделать условие «babble» в окне покоя между
EOF2 и следующим SOF, после чего xHCI выключает корневой порт целиком и
устройство отваливается:

    usb usb1-port1: disabled by hub (EMI?), re-enabling...
    usb 1-1: USB disconnect, device number 2

Бит GUCTL1.LOA_FILTER_EN требует, чтобы условие подтвердилось трижды подряд,
и отсекает ложные срабатывания. Свойство работает только вместе с правкой
драйвера (drivers/usb/dwc3/core.c), то есть с ядром нашей сборки.

База — DTB с Type-C, чтобы не потерять правку USB host и задержку динамика.
Собирается из ПОСТАВЛЯЕМОГО DTB, а не из исходников: у автора есть три
правки, сделанные после публикации дерева (см. docs/android-syachos.md).
"""
import subprocess, sys, os

A = "/mnt/t/Dump/RG52Mini/android/"
SRC = A + "rk3562-rg52mini-typec.dtb"
DST = A + "rk3562-rg52mini-usb.dtb"
W = A + "usbwork/"
os.makedirs(W, exist_ok=True)

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit("сбой %s%s%s" % (" ".join(cmd), chr(10), r.stderr))
    return r

if not os.path.exists(SRC):
    sys.exit("нет %s — сначала mktypec.py" % SRC)

run(["dtc", "-I", "dtb", "-O", "dts", "-o", W + "orig.dts", SRC])
s = open(W + "orig.dts").read()

if "loa-filter-en-quirk" in s:
    sys.exit("свойство уже есть")

# узел контроллера: тот, где уже стоит usb-role-switch (наша правка Type-C)
anchor = "snps,dis_rxdet_inp3_quirk;"
n = s.count(anchor)
if n != 1:
    sys.exit("ожидался ровно один узел dwc3, найдено %d" % n)
s = s.replace(anchor, anchor + chr(10) + "\t\t\tsnps,loa-filter-en-quirk;", 1)

# 2. защита от перегрева: выше 95 C ограничить процессор режимами до 1.1 В.
# Без rockchip,high-temp порог остаётся INT_MAX, то есть монитор системы
# не включается никогда, и единственным ограничителем работает термополитика,
# регулирующая к 85 C. Значения из ветки develop-6.1; драйвер в 5.10 оба
# свойства уже разбирает.
if "rockchip,high-temp" not in s:
    a2 = "rockchip,low-temp-min-volt = <0x100590>;"
    if s.count(a2) != 1:
        sys.exit("не нашёл узел таблицы частот процессора (%d совпадений)" % s.count(a2))
    s = s.replace(a2, a2 + chr(10) +
                  "		rockchip,high-temp = <0x17318>;" + chr(10) +
                  "		rockchip,high-temp-max-volt = <0x10c8e0>;", 1)

open(W + "new.dts", "w").write(s)
run(["dtc", "-I", "dts", "-O", "dtb", "-o", DST, W + "new.dts"])

back = run(["dtc", "-I", "dtb", "-O", "dts", DST]).stdout
assert "loa-filter-en-quirk" in back, "фильтр babble не попал в DTB"
assert "rockchip,high-temp" in back, "защита от перегрева не попала в DTB"
assert "husb311" in back, "потерян контроллер Type-C"
assert "spk-mute-delay-ms" in back, "потеряна задержка динамика"
assert "usb-role-switch" in back, "потеряно переключение роли USB"
print("готов %s, %d байт (было %d)" %
      (os.path.basename(DST), os.path.getsize(DST), os.path.getsize(SRC)))
