#!/usr/bin/env python3
"""Ставит в образ наш демон геймпада rgp2pad2 вместо авторского rgp2pad.

Разбор: docs/10-rgp2pad2-mouse.md

Кладёт в раздел vendor:
  * /bin/rgp2pad            — наш демон (авторский сохраняется как .orig);
  * /bin/rgp2pad-killall.sh — скрипт «закрыть всё», который демон зовёт по
                              аккорду Select+Start.

Служба init не трогается: /vendor/etc/init/rgp2pad.rc запускает файл по имени
rgp2pad, поэтому подмена файла — это и есть подмена демона. Откат — вернуть
.orig на место.

Метки SELinux не ставятся намеренно: у авторского файла её нет
(u:object_r:unlabeled:s0), ставить свою — менять поведение.

Путь образа можно передать первым аргументом.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
OUT = A + "rgp2pad2/out/"
IMG = sys.argv[1] if len(sys.argv) > 1 else A + "SyachOS-RG52Mini-V1.0.317m3.0.img"
P5_OFF, P5_LEN = 1698693120, 267046912

FILES = [("rgp2pad2", "rgp2pad"), ("rgp2pad-killall.sh", "rgp2pad-killall.sh")]

for src, _ in FILES:
    if not os.path.exists(OUT + src):
        sys.exit("нет " + OUT + src + " — сначала rgp2pad2/build.sh")
if not os.path.exists(IMG):
    sys.exit("нет " + IMG)

print("образ:", os.path.basename(IMG))
tmp = tempfile.mkdtemp()
p5 = os.path.join(tmp, "p5.img")
with open(IMG, "rb") as f:
    f.seek(P5_OFF)
    open(p5, "wb").write(f.read(P5_LEN))

# Авторский демон сохраняется один раз: при повторном запуске .orig уже лежит
# в образе, и перезаписывать его нашим же файлом нельзя.
have_orig = "File not found" not in subprocess.run(
    ["debugfs", "-R", "stat /bin/rgp2pad.orig", p5],
    capture_output=True, text=True).stderr

lines = ["cd /bin"]
if have_orig:
    print("  rgp2pad.orig уже в образе, сохранение пропускаю")
else:
    orig = os.path.join(tmp, "rgp2pad.orig")
    subprocess.run(["debugfs", "-R", "dump /bin/rgp2pad " + orig, p5],
                   capture_output=True)
    if not os.path.getsize(orig):
        sys.exit("не удалось вынуть авторский /vendor/bin/rgp2pad")
    lines += ["write %s rgp2pad.orig" % orig, "sif /bin/rgp2pad.orig mode 0100755"]
    print("  авторский сохранён как rgp2pad.orig, %d байт" % os.path.getsize(orig))

for src, dst in FILES:
    lines += ["rm " + dst, "write %s %s" % (OUT + src, dst),
              "sif /bin/%s mode 0100755" % dst]
lines.append("quit")
subprocess.run(["debugfs", "-w", "-f", "-", p5], input="\n".join(lines) + "\n",
               capture_output=True, text=True)

r = subprocess.run(["e2fsck", "-fp", p5], capture_output=True, text=True)
print("e2fsck vendor:", r.stdout.strip().splitlines()[-1])
if r.returncode not in (0, 1):
    sys.exit("e2fsck недоволен")

for src, dst in FILES:
    back = os.path.join(tmp, "back_" + dst)
    subprocess.run(["debugfs", "-R", "dump /bin/%s %s" % (dst, back), p5],
                   capture_output=True)
    if open(back, "rb").read() != open(OUT + src, "rb").read():
        sys.exit("%s записался неверно" % dst)
    print("  %-22s %9d байт, сверен через ФС" % (dst, os.path.getsize(OUT + src)))

with open(IMG, "r+b") as f:
    f.seek(P5_OFF)
    f.write(open(p5, "rb").read())
    f.flush()
print("образ готов")
