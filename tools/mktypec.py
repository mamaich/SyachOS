#!/usr/bin/env python3
"""Возвращает в device tree контроллер Type-C HUSB311 — чинит USB host.

На плате стоит HUSB311 (Hynetek) на i2c@ffa10000, адрес 0x4e. Роль USB на
разъёме Type-C определяется по линиям CC через него; ID-пина здесь нет.
В DTB от EmuELEC этот узел есть, в андроидном автор его потерял, а dwc3
оставил на extcon от usb2-phy, то есть ждать сигнала, которого не будет.
Итог: контроллер вечно в режиме периферии, хост не поднимается.

Драйвер в андроидном ядре уже вкомпилирован (CONFIG_TYPEC_HUSB311=y,
TYPEC_TCPM, USB_ROLE_SWITCH), не хватает только описания.

Значения скопированы из рабочего DTB EmuELEC той же платы, phandle
пересчитаны под андроидное дерево:
    GPIO0 (interrupt-parent)  0x3d -> 0x3c
    pcfg-pull-up              0xd7 -> 0xcf
    OTG_SWITCH (vbus-supply)  0xbe -> 0x166
Новые phandle взяты от 0x300 (максимальный занятый в дереве - 689).

База - DTB, в котором уже есть spk-mute-delay-ms, чтобы не потерять правку.
"""
import subprocess, sys, os, re

A = "/mnt/t/Dump/RG52Mini/android/"
SRC = A + "rk3562-rg52mini-spkdelay.dtb"
DST = A + "rk3562-rg52mini-typec.dtb"
W = A + "tcwork/"
os.makedirs(W, exist_ok=True)

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("сбой %s\n%s" % (" ".join(cmd), r.stderr))
    return r

run(["dtc", "-I", "dtb", "-O", "dts", "-o", W + "orig.dts", SRC])
s = open(W + "orig.dts").read()

PH_PIN, PH_TC, PH_TC_EP, PH_DWC_EP = "0x300", "0x301", "0x302", "0x303"
for p in (PH_PIN, PH_TC, PH_TC_EP, PH_DWC_EP):
    if "phandle = <%s>" % p in s:
        sys.exit("phandle %s уже занят" % p)

# 1. вывод прерывания Type-C. Вставляем ПОСЛЕ свойств pinctrl:
#    в device tree свойства обязаны предшествовать подузлам.
anchor = "\t\tphandle = <0xcb>;\n"
if s.count(anchor) != 1:
    sys.exit("не нашёл конец свойств pinctrl")
pin_node = anchor + """
\t\tusb-typec {

\t\t\tusbc0-int {
\t\t\t\trockchip,pins = <0x00 0x0f 0x00 0xcf>;
\t\t\t\tphandle = <%s>;
\t\t\t};
\t\t};
""" % PH_PIN
s = s.replace(anchor, pin_node, 1)

# 2. шина i2c@ffa10000: включить и повесить контроллер
m = re.search(r"\n\ti2c@ffa10000 \{\n(.*?)\n\t\};\n", s, re.S)
if not m:
    sys.exit("не нашёл i2c@ffa10000")
body = m.group(1)
if 'status = "disabled";' not in body:
    sys.exit("i2c@ffa10000 уже не disabled")
newbody = body.replace('status = "disabled";', 'status = "okay";', 1) + """

\t\thusb311@4e {
\t\t\tcompatible = "hynetek,husb311";
\t\t\treg = <0x4e>;
\t\t\tinterrupt-parent = <0x3c>;
\t\t\tinterrupts = <0x0f 0x08>;
\t\t\tpinctrl-names = "default";
\t\t\tpinctrl-0 = <%s>;
\t\t\tvbus-supply = <0x166>;
\t\t\tstatus = "okay";
\t\t\tphandle = <%s>;

\t\t\tports {
\t\t\t\t#address-cells = <0x01>;
\t\t\t\t#size-cells = <0x00>;

\t\t\t\tport@0 {
\t\t\t\t\treg = <0x00>;

\t\t\t\t\tendpoint@0 {
\t\t\t\t\t\tremote-endpoint = <%s>;
\t\t\t\t\t\tphandle = <%s>;
\t\t\t\t\t};
\t\t\t\t};
\t\t\t};

\t\t\tconnector {
\t\t\t\tcompatible = "usb-c-connector";
\t\t\t\tlabel = "USB-C";
\t\t\t\tdata-role = "dual";
\t\t\t\tpower-role = "dual";
\t\t\t\ttry-power-role = "sink";
\t\t\t\top-sink-microwatt = <0xf4240>;
\t\t\t\tsink-pdos = <0x401912c>;
\t\t\t\tsource-pdos = <0x260190c8>;
\t\t\t};
\t\t};""" % (PH_PIN, PH_TC, PH_DWC_EP, PH_TC_EP)
s = s[:m.start(1)] + newbody + s[m.end(1):]

# 3. dwc3: с extcon на usb-role-switch
m = re.search(r"\n\t\tusb@fe500000 \{\n(.*?)\n\t\t\};\n", s, re.S)
if not m:
    sys.exit("не нашёл usb@fe500000")
body = m.group(1)
if "\t\t\textcon = <0x36>;\n" not in body:
    sys.exit("не нашёл extcon в dwc3")
newbody = body.replace("\t\t\textcon = <0x36>;\n", "\t\t\tusb-role-switch;\n", 1) + """

\t\t\tport {
\t\t\t\t#address-cells = <0x01>;
\t\t\t\t#size-cells = <0x00>;

\t\t\t\tendpoint@0 {
\t\t\t\t\treg = <0x00>;
\t\t\t\t\tremote-endpoint = <%s>;
\t\t\t\t\tphandle = <%s>;
\t\t\t\t};
\t\t\t};""" % (PH_TC_EP, PH_DWC_EP)
s = s[:m.start(1)] + newbody + s[m.end(1):]

open(W + "new.dts", "w").write(s)

r = subprocess.run(["dtc", "-I", "dts", "-O", "dtb", "-o", DST, W + "new.dts"],
                   capture_output=True, text=True)
if r.returncode != 0:
    sys.exit("dtc не собрал:\n" + r.stderr)
warn = [l for l in r.stderr.splitlines() if l.strip()]
if warn:
    print("предупреждения dtc:")
    for l in warn[:8]:
        print("   ", l)
print("собрано: %d байт (база %d)" % (os.path.getsize(DST), os.path.getsize(SRC)))

run(["dtc", "-I", "dtb", "-O", "dts", "-o", W + "back.dts", DST])
d = subprocess.run(["diff", W + "orig.dts", W + "back.dts"], capture_output=True, text=True)
print("\n=== изменения в дереве:")
print(d.stdout)
