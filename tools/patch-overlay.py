#!/usr/bin/env python3
"""Makes SBC the default A2DP codec by adding an RRO overlay to the image.

The Bluetooth app takes codec priorities from its own resources; there is no
system property for them (it only reads avrcpversion, mapversion, factoryreset
and pts). So the only clean way is a runtime resource overlay that lowers
AAC below SBC. AAC stays selectable by hand - it is just no longer preferred.

Why bother: AAC's encoder plus decoder lookahead adds roughly 50-90 ms over
SBC, which is audible as extra lip-sync delay. Note this does NOT show up in
`Threadloop write latency` or in the latency AudioFlinger reports - both
measure the path *before* the encoder.

The overlay is built by mkoverlay.sh and declares android:isStatic="true",
which is how every stock overlay in this ROM is switched on: no config file
and no state in /data, so it survives a reflash.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = A + "SyachOS-RG52Mini-V1.0.317-aic8800-wifi-bt.img"
APK = A + "RG52MiniBtCodecOverlay.apk"
P4_OFF, P4_LEN = 121634816, 1577058304
DST = "/system/product/overlay/RG52MiniBtCodecOverlay.apk"

if not os.path.exists(APK):
    sys.exit("нет %s - сначала mkoverlay.sh" % APK)

tmp = tempfile.mkdtemp()
part = os.path.join(tmp, "p4.img")
with open(IMG, "rb") as f:
    f.seek(P4_OFF)
    open(part, "wb").write(f.read(P4_LEN))

# /product - символьная ссылка на /system/product, поэтому путь полный
script = ("cd /system/product/overlay\nwrite %s RG52MiniBtCodecOverlay.apk\n"
          "sif %s mode 0100644\nquit\n" % (APK, DST))
subprocess.run(["debugfs", "-w", "-f", "-", part], input=script,
               capture_output=True, text=True)
r = subprocess.run(["e2fsck", "-fp", part], capture_output=True, text=True)
print("e2fsck:", r.stdout.strip().splitlines()[-1])

back = os.path.join(tmp, "back.apk")
subprocess.run(["debugfs", "-R", "dump %s %s" % (DST, back), part],
               capture_output=True)
if open(back, "rb").read() != open(APK, "rb").read():
    sys.exit("оверлей записался неверно")
print("оверлей на месте, %d байт, проверен через ФС" % os.path.getsize(back))

with open(IMG, "r+b") as f:
    f.seek(P4_OFF)
    f.write(open(part, "rb").read())
    f.flush()
print("образ обновлён")
