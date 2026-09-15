#!/usr/bin/env python3
"""Убирает вывод ядра **на экран**, оставляя его в последовательном порту.

История этой правки поучительна, поэтому записана целиком.

Задумывалась она наоборот: убрать `console=ttyFIQ0,1500000` и `earlycon` из
`extlinux.conf`, чтобы сообщения не выталкивались в порт на 1,5 Мбод, к
которому никто не подключён. Вышло иначе. U-Boot собирает строку ядра сам и
**подставляет свою консоль вместо первого найденного `console=`**, а не
дописывает вторую. В авторской строке консолей было две:

    console=ttyFIQ0,1500000 console=tty1

и подменялась первая, а экранная оставалась. Убрав `ttyFIQ0`, мы оставили
единственный `console=tty1` — и U-Boot подменил **его**. В итоге пропал вывод
на экран, а порт остался.

Позже выяснилось, что так и лучше: с версии `m5.0` при загрузке показывается
логотип ([11](../docs/11-boot-logo.md)), и текст поверх него только мешает —
тем более что `fbcon` при развороте `fbcon=rotate:1` не умеет прокрутку и
затирает нижнюю строку. Поэтому правка оставлена, но с честным описанием:
**она убирает консоль с экрана, а не из UART.**

Убрать консоль из порта пробовали отдельно — выключением
`CONFIG_FIQ_DEBUGGER_CONSOLE` и `CONFIG_SERIAL_EARLYCON` в ядре (иначе никак:
консоль FIQ-отладчика объявлена с флагом `CON_ENABLED` и включается сама,
а `earlycon=` дописывает U-Boot). Это работает, но смысла не имеет: время
выключения от неё не зависит — шесть секунд там тратит уборка binder, а не
порт. Зато без консоли в системе не остаётся `/dev/console`, и два сервиса
`init` падают с «Couldn't open console». Поэтому откачено.

Правится `extlinux.conf` в FAT-разделе p3 по месту, с добиванием до исходной
длины, чтобы запись в каталоге FAT осталась верной.
"""
import sys

IMG = sys.argv[1] if len(sys.argv) > 1 else \
    "/mnt/t/Dump/RG52Mini/android/SyachOS-RG52Mini-V1.0.317m5.0.img"
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

    # Хвост области — заполнитель из переводов строки; длина файла не меняется.
    body = new.rstrip(b"\n")
    if len(body) > len(old):
        sys.exit("новый текст длиннее области: %d при %d" % (len(body), len(old)))
    new = body + b"\n" * (len(old) - len(body))

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
