#!/usr/bin/env python3
"""Проверяет, что ссылки в новом DTB указывают на нужные узлы."""
import re, subprocess, sys
dtb = sys.argv[1]
dts = subprocess.run(["dtc","-I","dtb","-O","dts",dtb],capture_output=True,text=True).stdout
tree, path = {}, []
for raw in dts.split("\n"):
    l = raw.strip()
    if not l or l.startswith(("/dts-v1/","//","/memreserve/")): continue
    if l.endswith("{"): path.append(l[:-1].strip()); tree.setdefault("/".join(path), {})
    elif l == "};":
        if path: path.pop()
    elif l.endswith(";"):
        b = l[:-1]
        if "=" in b:
            k,v = b.split("=",1); tree.setdefault("/".join(path),{})[k.strip()] = v.strip()
        else: tree.setdefault("/".join(path),{})[b.strip()] = True
ph = {int(v[1:-1],16): p for p,d in tree.items() for k,v in d.items()
      if k == "phandle" and isinstance(v,str)}
def find(sub):
    return [p for p in tree if p.endswith(sub)]
def deref(p, prop, idx=0):
    v = tree[p].get(prop)
    if not isinstance(v,str): return None
    cells = re.findall(r"0x[0-9a-f]+", v)
    if len(cells) <= idx: return None
    return ph.get(int(cells[idx],16))

tc  = find("/i2c@ffa10000/husb311@4e")[0]
tcep= find("/husb311@4e/ports/port@0/endpoint@0")[0]
dw  = find("/usbdrd/usb@fe500000")[0]
dwep= find("/usb@fe500000/port/endpoint@0")[0]
cod = [p for p in tree if p.endswith("/pmic@20/codec")][0]
snd = [p for p in tree if p.endswith("/rk817-sound")][0]
tim = [p for p in tree if p.endswith("/display-timings/timing0")][0]

def show(t, ok):  print(("  OK   " if ok else "  НЕТ  ") + t)

print("=== контроллер Type-C")
show("узел husb311@4e на месте: " + tc, True)
show("interrupt-parent -> %s" % deref(tc,"interrupt-parent"), (deref(tc,"interrupt-parent") or "").endswith("gpio@ff260000"))
show("pinctrl-0 -> %s" % deref(tc,"pinctrl-0"), (deref(tc,"pinctrl-0") or "").endswith("usbc0-int"))
show("vbus-supply -> %s" % deref(tc,"vbus-supply"), (deref(tc,"vbus-supply") or "").endswith("OTG_SWITCH"))
show("interrupts = %s (пин 15, level low)" % tree[tc].get("interrupts"), tree[tc].get("interrupts")=="<0x0f 0x08>")
show("i2c@ffa10000 включена", tree[[p for p in tree if p.endswith("/i2c@ffa10000")][0]].get("status")=='"okay"')

print("=== связка ролей")
show("endpoint контроллера -> %s" % deref(tcep,"remote-endpoint"), deref(tcep,"remote-endpoint")==dwep)
show("endpoint dwc3 -> %s" % deref(dwep,"remote-endpoint"), deref(dwep,"remote-endpoint")==tcep)
show("у dwc3 есть usb-role-switch", tree[dw].get("usb-role-switch") is True)
show("у dwc3 больше нет extcon", "extcon" not in tree[dw])

print("=== звук")
show("spk-mute-delay-ms = %s" % tree[cod].get("spk-mute-delay-ms"), tree[cod].get("spk-mute-delay-ms")=="<0x64>")
g = deref(cod,"spk-ctl-gpios")
show("spk-ctl-gpios -> %s пин %s" % (g, re.findall(r"0x[0-9a-f]+", tree[cod].get("spk-ctl-gpios",""))[1:2]),
     (g or "").endswith("gpio@ffad0000") or (g or "").endswith("gpio@ff630000") or g is not None)
show("spk-con-gpios убран из звуковой карты", "spk-con-gpios" not in tree[snd])

print("=== панель")
show("vfront-porch = %s (ожидаем 0x1f)" % tree[tim].get("vfront-porch"), tree[tim].get("vfront-porch")=="<0x1f>")
