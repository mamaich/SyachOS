#!/bin/bash
# Собирает патченый образ SyachOS с Wi-Fi и Bluetooth для AIC8800D80.
# Запускать в WSL:  bash /mnt/t/Dump/RG52Mini/android/patch-bt.sh
#
# Вход:  SyachOS-RG52Mini-V1.0.317-20260707.img   (стоковый распакованный)
#        bt-payload/                              (файлы, снятые с рабочего устройства)
# Выход: SyachOS-RG52Mini-V1.0.317m1.0.img
#
# Правится два раздела: p4 system (system-as-root) и p5 vendor.
# Смещения из GPT образа; при смене версии образа их надо перечитать.
set -e

A=/mnt/t/Dump/RG52Mini/android
BASE=$A/SyachOS-RG52Mini-V1.0.317-aic8800-patched.img   # уже с Wi-Fi
OUT=$A/SyachOS-RG52Mini-V1.0.317m1.0.img
P=$A/parts
B=$A/bt-payload

P4_OFF=121634816   ; P4_LEN=1577058304   # system
P5_OFF=1698693120  ; P5_LEN=267046912    # vendor

V=$P/p5_vendor.img
S=$P/p4_system.img

echo "[1/6] извлечение разделов"
mkdir -p $P
dd if=$BASE of=$V bs=4M iflag=skip_bytes,count_bytes skip=$P5_OFF count=$P5_LEN status=none
dd if=$BASE of=$S bs=4M iflag=skip_bytes,count_bytes skip=$P4_OFF count=$P4_LEN status=none

echo "[2/6] сохранение оригиналов"
debugfs -R "dump /lib64/libbt-vendor.so $B/libbt-vendor.so.orig" $V 2>/dev/null
debugfs -R "dump /lib64/libbt-vendor-seekwave.so $B/libbt-vendor-seekwave.so.orig" $V 2>/dev/null
debugfs -R "dump /system/etc/sysconfig/rg52-no-tv.xml $B/rg52-no-tv.xml.orig" $S 2>/dev/null

echo "[3/6] правка vendor"
debugfs -w -f - $V >/dev/null <<DBG
cd /lib/modules
rm aic8800_bsp.ko
rm aic8800_fdrv.ko
write $B/aic8800_bsp.ko aic8800_bsp.ko
write $B/aic8800_fdrv.ko aic8800_fdrv.ko
cd /lib64
write $B/libbt-vendor.so.orig libbt-vendor.so.orig
write $B/libbt-vendor-seekwave.so.orig libbt-vendor-seekwave.so.orig
rm libbt-vendor.so
rm libbt-vendor-seekwave.so
write $B/libbt-vendor.so libbt-vendor.so
write $B/libbt-vendor-seekwave.so libbt-vendor-seekwave.so
ea_set libbt-vendor.so security.selinux "u:object_r:vendor_file:s0\000"
ea_set libbt-vendor-seekwave.so security.selinux "u:object_r:vendor_file:s0\000"
ea_set libbt-vendor.so.orig security.selinux "u:object_r:vendor_file:s0\000"
ea_set libbt-vendor-seekwave.so.orig security.selinux "u:object_r:vendor_file:s0\000"
cd /
rm build.prop
write $B/build.prop build.prop
sif /lib/modules/aic8800_bsp.ko mode 0100644
sif /lib/modules/aic8800_fdrv.ko mode 0100644
sif /lib64/libbt-vendor.so mode 0100644
sif /lib64/libbt-vendor-seekwave.so mode 0100644
sif /lib64/libbt-vendor.so.orig mode 0100644
sif /lib64/libbt-vendor-seekwave.so.orig mode 0100644
sif /build.prop mode 0100644
quit
DBG

# ВАЖНО: p4 - system-as-root, /etc в нём символьная ссылка,
# в debugfs надо писать полный путь /system/etc/...
echo "[4/6] правка system"
debugfs -w -f - $S >/dev/null <<DBG
cd /system/etc
write $B/rg52-no-tv.xml.orig rg52-no-tv.xml.orig
cd /system/etc/sysconfig
rm rg52-no-tv.xml
write $B/rg52-no-tv.xml rg52-no-tv.xml
sif /system/etc/rg52-no-tv.xml.orig mode 0100644
sif /system/etc/sysconfig/rg52-no-tv.xml mode 0100644
quit
DBG

e2fsck -fp $V
e2fsck -fp $S

echo "[5/6] сборка образа"
rm -f $OUT
cp $BASE $OUT
dd if=$S of=$OUT bs=4M conv=notrunc oflag=seek_bytes seek=$P4_OFF status=none
dd if=$V of=$OUT bs=4M conv=notrunc oflag=seek_bytes seek=$P5_OFF status=none
sync

echo "[6/6] проверка готового образа"
T=$(mktemp -d)
dd if=$OUT of=$T/v.img bs=4M iflag=skip_bytes,count_bytes skip=$P5_OFF count=$P5_LEN status=none
dd if=$OUT of=$T/s.img bs=4M iflag=skip_bytes,count_bytes skip=$P4_OFF count=$P4_LEN status=none
e2fsck -fp $T/v.img
e2fsck -fp $T/s.img
debugfs -R "dump /lib/modules/aic8800_bsp.ko $T/a" $T/v.img >/dev/null 2>&1
debugfs -R "dump /lib/modules/aic8800_fdrv.ko $T/b" $T/v.img >/dev/null 2>&1
debugfs -R "dump /lib64/libbt-vendor.so $T/c" $T/v.img >/dev/null 2>&1
debugfs -R "dump /lib64/libbt-vendor-seekwave.so $T/d" $T/v.img >/dev/null 2>&1
debugfs -R "dump /build.prop $T/e" $T/v.img >/dev/null 2>&1
debugfs -R "dump /etc/init.insmod.cfg $T/f" $T/v.img >/dev/null 2>&1
debugfs -R "dump /system/etc/sysconfig/rg52-no-tv.xml $T/g" $T/s.img >/dev/null 2>&1
for p in a:aic8800_bsp.ko b:aic8800_fdrv.ko c:libbt-vendor.so \
         d:libbt-vendor-seekwave.so e:build.prop f:init.insmod.cfg g:rg52-no-tv.xml; do
  k=${p%%:*}; n=${p#*:}
  if cmp -s $T/$k $B/$n; then echo "OK   $n"; else echo "FAIL $n"; fi
done
rm -rf $T
ls -la $OUT
sha256sum $OUT | tee $OUT.sha256
