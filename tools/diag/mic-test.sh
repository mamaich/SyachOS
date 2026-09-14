#!/system/bin/sh
T=/data/local/tmp
R=/sys/kernel/debug/regmap/0-0020-rk817-codec/registers
$T/tinymix set "Capture MIC Path" "Main Mic" >/dev/null
echo "тракт записи: $($T/tinymix get "Capture MIC Path" | tr ',' '\n' | grep '>' )"
for rate in 48000 16000; do
  echo "--- $rate Гц"
  rm -f $T/rec_$rate.wav
  $T/tinycap $T/rec_$rate.wav -D 0 -d 0 -c 2 -r $rate -b 16 -t 3 > $T/cap_$rate.log 2>&1 &
  P=$!
  sleep 1.5
  echo "    регистр АЦП 1e = $(grep -E '^1e:' $R | cut -d' ' -f2)   (ожидается: 48к->02, 16к->01)"
  wait $P
  cat $T/cap_$rate.log
  echo "    файл: $(stat -c %s $T/rec_$rate.wav) байт"
done
$T/tinymix set "Capture MIC Path" "MIC OFF" >/dev/null
