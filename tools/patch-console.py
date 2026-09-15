#!/usr/bin/env python3
"""Убирает последовательную консоль из загрузочной строки ядра.

Каждое сообщение ядра синхронно выталкивается в UART на 1,5 Мбод; кабеля
к этим площадкам нет, а лог всё равно читается через dmesg и pstore. Убираем:

    console=ttyFIQ0,1500000                  консоль ядра в UART
    earlycon=uart8250,mmio32,0xff210000      она же на раннем этапе загрузки

`console=tty1` остаётся: это вывод на экран, по нему видно панику, если она
случится до старта Android. `printk.devkmsg=on` тоже остаётся — через /dev/kmsg
пишет наш демон геймпада.

Правится extlinux.conf в FAT-разделе p3 по месту, с добиванием до исходной
длины, чтобы запись в каталоге FAT осталась верной.

Цена: если когда-нибудь припаяетесь к UART, паники по проводу видно не будет —
строку придётся вернуть.
"""
import sys

IMG = sys.argv[1] if len(sys.argv) > 1 else \
    "/mnt/t/Dump/RG52Mini/android/SyachOS-RG52Mini-V1.0.317m4.0.img"
P3_OFF, P3_LEN = 16777216, 103809024

DROP = [b"console=ttyFIQ0,1500000 ",
        b"earlycon=uart8250,mmio32,0xff210000 "]

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
    print("копий extlinux.conf найдено:", len(hits))
    if len(hits) != 1:
        sys.exit("ожидалась ровно одна копия")

    at = hits[0]
    marker = b"androidboot.selinux=permissive"
    end = blob.find(marker, at)
    if end < 0:
        sys.exit("конец строки APPEND не найден")
    end += len(marker)
    while end < len(blob) and blob[end] in (0x0A, 0x0D):
        end += 1
    old = blob[at:end]

    new = old
    for d in DROP:
        if d in new:
            new = new.replace(d, b"")
            print("  убрано:", d.decode().strip())
        else:
            print("  уже нет:", d.decode().strip())
    if new == old:
        print("правка не нужна")
        sys.exit(0)
    if len(new) > len(old):
        sys.exit("новый текст длиннее старого")
    new = new + b"\n" * (len(old) - len(new))

    f.seek(P3_OFF + at)
    f.write(new)
    f.flush()
    f.seek(P3_OFF + at)
    back = f.read(len(old))

print("--- строка теперь ---")
for line in back.decode().splitlines():
    if line.strip():
        print(line)
print("---------------------")
assert back == new, "сверка не сошлась"
print("OK")
