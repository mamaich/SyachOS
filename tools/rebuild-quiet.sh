#!/bin/bash
# Пересобирает модули aic8800 с выключенным отладочным выводом.
# Запускать в WSL:  bash /mnt/t/Dump/RG52Mini/android/rebuild-quiet.sh
#
# Штатное умолчание драйвера включает LOGINFO|LOGDEBUG|LOGTRACE|LOGFW, из-за
# чего он сыплет в лог ядра каждые 3 секунды и вытесняет всё полезное из
# кольцевого буфера. Параметр модуля aicwf_dbg_level менять на лету можно,
# но задать его постоянно через init.insmod.cfg нельзя: init.insmod.sh делает
# [ -f $name ] на всё, что после "insmod", так что аргументы ломают проверку.
# Поэтому правится умолчание в исходниках.
set -e

K=~/rg52/kernel_rk3562_rg52mini
A=$K/drivers/net/wireless/aic8800
F1=$A/aic8800_fdrv/rwnx_main.c
F2=$A/aic8800_bsp/aic_bsp_main.c

sed -i 's/^int aicwf_dbg_level = LOGERROR|LOGINFO|LOGDEBUG|LOGTRACE|LOGFW;/int aicwf_dbg_level = LOGERROR;/' $F1
sed -i 's/^int aicwf_dbg_level_bsp = LOGERROR|LOGINFO|LOGDEBUG|LOGTRACE;/int aicwf_dbg_level_bsp = LOGERROR;/' $F2
grep -n 'int aicwf_dbg_level' $F1 $F2

cd $K
export ARCH=arm64
export CROSS_COMPILE=$(ls -d ~/rg52/toolchain/*/bin/ | head -1)aarch64-none-linux-gnu-
make -j$(nproc) modules

O=~/rg52/out-syach-quiet; mkdir -p $O
for m in aic8800_bsp aic8800_fdrv; do
  cp $(find $A -name "$m.ko" | head -1) $O/$m.ko
  ${CROSS_COMPILE}strip --strip-debug $O/$m.ko
done
ls -la $O
# дальше: cp $O/*.ko /mnt/t/Dump/RG52Mini/android/bt-payload/ и patch-quiet.py
