#!/bin/bash
# Сборка rgp2pad2 под Android/aarch64, статически.
#
# Статически — потому что демон стартует из init очень рано, и зависеть от
# динамических библиотек vendor не хочется. Оригинал собран так же.
#
# Запускать в WSL:  bash /mnt/t/Dump/RG52Mini/android/rgp2pad2/build.sh
set -e

NDK=/home/mamaich/rg52/ndk/android-ndk-r27c
SRC_DIR=/mnt/t/Dump/RG52Mini/android/rgp2pad2
OUT=$SRC_DIR/out

CC=$(ls "$NDK"/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android*-clang \
     2>/dev/null | sort -V | tail -1)
[ -n "$CC" ] || { echo "не нашёл clang из NDK в $NDK"; exit 1; }

mkdir -p "$OUT"
echo "компилятор: $(basename "$CC")"

"$CC" -std=c11 -O2 -static -Wall -Wextra -Werror \
      -Wno-unused-parameter \
      -o "$OUT/rgp2pad2" "$SRC_DIR/rgp2pad2.c" -lm

cp "$SRC_DIR/rgp2pad-killall.sh" "$OUT/"
chmod 755 "$OUT/rgp2pad2" "$OUT/rgp2pad-killall.sh"

echo
echo "=== собрано ==="
ls -la "$OUT"
file "$OUT/rgp2pad2" | cut -c1-100
echo
echo "=== проверки ==="
echo -n "  статический: "; file "$OUT/rgp2pad2" | grep -q "statically linked" && echo да || echo НЕТ
echo -n "  свойства Android: "
"$NDK"/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm "$OUT/rgp2pad2" 2>/dev/null \
  | grep -qi "system_property_get" && echo да || echo НЕТ
