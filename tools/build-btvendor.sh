#!/bin/bash
# Сборка прослойки libbt-vendor.so для AIC8800D80 (см. docs/02-wifi-bluetooth.md).
#
# Нужен Android NDK r27c: библиотека грузится в процесс с Bionic, toolchain
# от ядра (aarch64-none-linux-gnu) слинкует её с glibc и она не загрузится.
# NDK ставится простой распаковкой, root не нужен:
#   mkdir -p ~/rg52/ndk && cd ~/rg52/ndk
#   unzip android-ndk-r27c-linux.zip
#
# Результат кладётся в $OUT и дальше попадает в образ через tools/patch-bt.sh
# (под двумя именами: libbt-vendor.so и libbt-vendor-seekwave.so).
set -e

RG=${RG:-/home/mamaich/rg52}
SRC=${SRC:-$RG/SyachOS/src/btvendor_aic.c}
OUT=${OUT:-$RG/out-syach}

CC=$(echo "$RG"/ndk/android-ndk-*/toolchains/llvm/prebuilt/linux-x86_64/bin)/aarch64-linux-android33-clang
[ -x "$CC" ] || { echo "!! NDK не найден: $CC"; exit 1; }

mkdir -p "$OUT"
"$CC" -shared -fPIC -O2 -Wall -Wextra -o "$OUT/libbt-vendor.so" "$SRC" -llog

ls -la "$OUT/libbt-vendor.so"
sz=$(stat -c %s "$OUT/libbt-vendor.so")
# Тот же размер проверяет tools/verify-image.sh. Разошлось — либо другой NDK,
# либо правка исходника; проверьте, что это ожидаемо.
[ "$sz" = 10056 ] && echo "размер совпал с эталонным (10056)" \
                  || echo "!! размер $sz, эталон 10056 — сверьте версию NDK"
