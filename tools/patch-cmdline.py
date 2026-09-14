#!/usr/bin/env python3
"""Reduce kernel console verbosity in the SyachOS image.

Patches extlinux.conf inside the FAT boot partition (p3) in place, padded to
the exact original length so the FAT directory entry stays valid.

Only change: "ignore_loglevel loglevel=8" -> "loglevel=4".
  ignore_loglevel forces EVERY message to the console regardless of level;
  loglevel=4 leaves only crit/alert/emerg/err.
Everything else (TIMEOUT 50, console=tty1, earlycon, fbcon) is left exactly as
the author had it - both boot failures we saw came from touching those.
"""
import sys

IMG = sys.argv[1] if len(sys.argv) > 1 else \
    "/mnt/t/Dump/RG52Mini/android/SyachOS-RG52Mini-V1.0.317m1.0.img"
P3_OFF, P3_LEN = 16777216, 103809024

with open(IMG, "r+b") as f:
    f.seek(P3_OFF)
    blob = f.read(P3_LEN)

    hits = []
    pos = 0
    while True:
        k = blob.find(b"DEFAULT Android13", pos)
        if k < 0:
            break
        hits.append(k)
        pos = k + 1
    print("extlinux.conf copies found:", len(hits))
    if len(hits) != 1:
        sys.exit("expected exactly one copy")

    at = hits[0]
    marker = b"androidboot.selinux=permissive"
    end = blob.find(marker, at)
    if end < 0:
        sys.exit("end of APPEND not found")
    end += len(marker)
    while end < len(blob) and blob[end] in (0x0A, 0x0D):
        end += 1
    old = blob[at:end]
    print("old file: %d bytes at partition offset %d" % (len(old), at))

    if b"ignore_loglevel" not in old:
        sys.exit("ignore_loglevel not present - already patched?")
    new = old.replace(b"ignore_loglevel loglevel=8", b"loglevel=4")
    if len(new) > len(old):
        sys.exit("new text longer than old")
    new = new + b"\n" * (len(old) - len(new))

    f.seek(P3_OFF + at)
    f.write(new)
    f.flush()

    f.seek(P3_OFF + at)
    back = f.read(len(old))

print("--- content now ---")
print(back.decode().rstrip())
print("-------------------")
assert back == new, "verify failed"
print("OK")
