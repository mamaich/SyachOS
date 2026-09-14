#!/usr/bin/env python3
"""Sets the extlinux menu timeout to 1 s (TIMEOUT 10) in the image.

extlinux TIMEOUT is in tenths of a second and U-Boot divides it by 10, so
anything below 10 can round down to 0 - which means "wait for a keypress
forever" and looks exactly like a dead device. 10 is the safe minimum.
Patched in place, same byte length, FAT metadata untouched.
"""
import sys
IMG = "/mnt/t/Dump/RG52Mini/android/SyachOS-RG52Mini-V1.0.317-aic8800-wifi-bt.img"
P3_OFF, P3_LEN = 16777216, 103809024

with open(IMG, "r+b") as f:
    f.seek(P3_OFF)
    blob = f.read(P3_LEN)
    at = blob.find(b"DEFAULT Android13")
    if at < 0 or blob.find(b"DEFAULT Android13", at + 1) >= 0:
        sys.exit("expected exactly one extlinux.conf")
    head = blob[at:at + 200]
    if b"\nTIMEOUT 10\n" in head:
        sys.exit("already TIMEOUT 10, nothing to do")
    if b"\nTIMEOUT 50\n" not in head:
        sys.exit("TIMEOUT 50 not found")
    new = head.replace(b"\nTIMEOUT 50\n", b"\nTIMEOUT 10\n")
    assert len(new) == len(head)
    f.seek(P3_OFF + at)
    f.write(new)
    f.flush()
    f.seek(P3_OFF + at)
    back = f.read(200)

assert back == new
print("\n".join(back.decode(errors="replace").splitlines()[:3]))
print("OK")
