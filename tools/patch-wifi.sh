#!/bin/bash
# Шаг 0 сборки: Wi-Fi. Кладёт в раздел vendor стокового образа модули aic8800,
# 15 блобов прошивки D80 и две строки insmod. Выход — базовый образ для шага 1
# (patch-bt.sh). Разбор: docs/02-wifi-bluetooth.md
#
# Вход:  SyachOS-RG52Mini-V1.0.317-20260707.img   (стоковый, распакованный)
#        fw-aic8800D80/                           (15 блобов, см. docs/00-pipeline.md)
#        собранные модули (tools/kbuild.sh -> ~/rg52/out-rg52)
# Выход: SyachOS-RG52Mini-V1.0.317-aic8800-patched.img
#
# Скрипт идемпотентен: повторный запуск переписывает файлы заново.
# Root не нужен: всё через debugfs.
set -e

A=${A:-/mnt/t/Dump/RG52Mini/android}
SRC=${SRC:-$A/SyachOS-RG52Mini-V1.0.317-20260707.img}
OUT=${OUT:-$A/SyachOS-RG52Mini-V1.0.317-aic8800-patched.img}
FW=${FW:-$A/fw-aic8800D80}
MOD=${MOD:-/home/mamaich/rg52/out-rg52}
P=${P:-$A/parts}

P5_OFF=1698693120 ; P5_LEN=267046912    # vendor, смещения из GPT этого образа
V=$P/p5_vendor_wifi.img

for f in "$SRC" "$MOD/aic8800_bsp.ko" "$MOD/aic8800_fdrv.ko"; do
  [ -f "$f" ] || { echo "!! нет файла: $f"; exit 1; }
done
n=$(ls "$FW" 2>/dev/null | wc -l)
[ "$n" = 15 ] || { echo "!! в $FW ожидается 15 блобов, найдено $n"; exit 1; }

echo "[1/5] извлечение vendor"
mkdir -p "$P"
dd if="$SRC" of="$V" bs=4M iflag=skip_bytes,count_bytes skip=$P5_OFF count=$P5_LEN status=none

echo "[2/5] модули и прошивки"
{
  echo "cd /lib/modules"
  echo "rm aic8800_bsp.ko"
  echo "rm aic8800_fdrv.ko"
  echo "write $MOD/aic8800_bsp.ko aic8800_bsp.ko"
  echo "write $MOD/aic8800_fdrv.ko aic8800_fdrv.ko"
  echo "sif /lib/modules/aic8800_bsp.ko mode 0100644"
  echo "sif /lib/modules/aic8800_fdrv.ko mode 0100644"
  # каталога может ещё не быть; rmdir не нужен, файлы перезаписываются поимённо
  echo "mkdir /etc/firmware/aic8800"
  echo "sif /etc/firmware/aic8800 mode 040755"
  for f in "$FW"/*; do
    b=$(basename "$f")
    echo "rm /etc/firmware/aic8800/$b"
    echo "write $f /etc/firmware/aic8800/$b"
    echo "sif /etc/firmware/aic8800/$b mode 0100644"
  done
  echo quit
} | debugfs -w -f - "$V" >/dev/null 2>&1

echo "[3/5] init.insmod.cfg"
T=$(mktemp -d)
debugfs -R "dump /etc/init.insmod.cfg $T/cfg" "$V" >/dev/null 2>&1
if grep -q 'aic8800_bsp' "$T/cfg"; then
  echo "     строки insmod уже есть, пропускаю"
else
  # Порядок обязателен: bsp поднимает питание чипа, fdrv должен идти после.
  # Ставим сразу после rk915, чтобы не менять остальной порядок загрузки.
  awk '{print} /rk915\.ko/ && !d {print "insmod /vendor/lib/modules/aic8800_bsp.ko";
        print "insmod /vendor/lib/modules/aic8800_fdrv.ko"; d=1}' "$T/cfg" > "$T/cfg.new"
  debugfs -w -f - "$V" >/dev/null <<DBG
cd /etc
rm init.insmod.cfg
write $T/cfg.new init.insmod.cfg
sif /etc/init.insmod.cfg mode 0100644
ea_set /etc/init.insmod.cfg security.selinux "u:object_r:vendor_configs_file:s0\000"
quit
DBG
fi

e2fsck -fp "$V"

echo "[4/5] сборка образа"
rm -f "$OUT"
cp "$SRC" "$OUT"
dd if="$V" of="$OUT" bs=4M conv=notrunc oflag=seek_bytes seek=$P5_OFF status=none
sync

echo "[5/5] проверка"
dd if="$OUT" of="$T/v.img" bs=4M iflag=skip_bytes,count_bytes skip=$P5_OFF count=$P5_LEN status=none
e2fsck -fp "$T/v.img"
ok=1
for m in aic8800_bsp.ko aic8800_fdrv.ko; do
  debugfs -R "dump /lib/modules/$m $T/x" "$T/v.img" >/dev/null 2>&1
  cmp -s "$T/x" "$MOD/$m" && echo "OK   $m" || { echo "FAIL $m"; ok=0; }
done
for f in "$FW"/*; do
  b=$(basename "$f")
  debugfs -R "dump /etc/firmware/aic8800/$b $T/x" "$T/v.img" >/dev/null 2>&1
  cmp -s "$T/x" "$f" || { echo "FAIL $b"; ok=0; }
done
[ $ok = 1 ] && echo "OK   15 блобов прошивки"
debugfs -R "dump /etc/init.insmod.cfg $T/y" "$T/v.img" >/dev/null 2>&1
grep -c 'aic8800' "$T/y" | grep -q '^2$' && echo "OK   init.insmod.cfg: две строки" \
                                         || { echo "FAIL init.insmod.cfg"; ok=0; }
grep -n 'rk915\|aic8800' "$T/y"
rm -rf "$T"
[ $ok = 1 ] || { echo; echo "!! есть расхождения"; exit 1; }
echo
ls -la "$OUT"
