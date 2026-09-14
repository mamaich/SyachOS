#!/system/bin/sh
# Честный измеритель без atrace: 20 раз в секунду пишет состояние потока
# композитора и счётчик прерываний кадровой развёртки. Потерь событий нет.
D=/data/local/tmp/frz5
rm -rf $D; mkdir -p $D; touch $D/davey.log
echo $$ > /data/local/tmp/frz5.pid

HW=$(pgrep -f "hardware.graphics.composer" | head -1)
CT=""
for T in /proc/$HW/task/*; do
  [ "$(cat $T/comm 2>/dev/null)" = "drm-compositor" ] && CT=${T##*/}
done
SF=$(pgrep -x surfaceflinger)
echo "композитор=$HW/$CT surfaceflinger=$SF" > $D/status
[ -z "$CT" ] && { echo "поток не найден" >> $D/status; exit 1; }
ST=/proc/$HW/task/$CT/stat

(logcat -c 2>/dev/null; logcat -b main -v time 2>/dev/null | grep --line-buffered Davey >> $D/davey.log) &

while true; do
  read up rest < /proc/uptime
  s=$(cut -d')' -f2 $ST 2>/dev/null | awk '{print $1}')
  v=$(awk '/ff400000.vop/{print $2}' /proc/interrupts)
  echo "$up $s $v" >> $D/samples
  sleep 0.05
done
