#!/system/bin/sh
# Ловушка фриза v3: главное — стек приложения в пользовательском пространстве.
D=/data/local/tmp/frz3
rm -rf $D; mkdir -p $D; touch $D/davey.log
echo $$ > /data/local/tmp/frz3.pid
CATS="sched irq gfx view sync binder_driver freq"
MAXDUMP=6

atrace --async_stop -o /dev/null >/dev/null 2>&1
atrace --async_start -c -b 8000 $CATS >/dev/null 2>&1
echo "старт, atrace rc=$?" > $D/status

(logcat -c 2>/dev/null; logcat -b main -v time 2>/dev/null | grep --line-buffered Davey >> $D/davey.log) &

snap() {
  S=$D/$1; mkdir -p $S
  cat /proc/uptime > $S/uptime
  # 1. САМОЕ ВАЖНОЕ и самое быстрое: стеки всех потоков зависшего приложения
  timeout 6 debuggerd -b $APP > $S/bt.app 2>&1
  # 2. то же для SurfaceFlinger — для сравнения
  timeout 6 debuggerd -b $SFPID > $S/bt.sf 2>&1
  # 3. что заблокировано в ядре
  ps -AT -o s,pid,tid,cmd 2>/dev/null > $S/psT
  awk '$1=="D"{print $2" "$3}' $S/psT | while read p t; do
    echo "== $p/$t $(cat /proc/$p/task/$t/comm 2>/dev/null)"; cat /proc/$p/task/$t/stack 2>/dev/null
  done > $S/dstate 2>&1
  grep -E "vop|mali|dma|rga" /proc/interrupts > $S/irq 2>&1
  cat /proc/pressure/cpu /proc/pressure/memory /proc/pressure/io > $S/pressure 2>&1
  cat /sys/kernel/debug/dri/0/summary > $S/dri 2>&1
  dmesg | tail -40 > $S/dmesg 2>&1
}

prev=-1; same=0; ndump=0; cool=0; prevdavey=0; good=0
while true; do
  read up rest < /proc/uptime
  v=$(awk '/ff400000.vop/{print $2}' /proc/interrupts)
  echo "$up $v" >> $D/irq.log
  dv=$(wc -l < $D/davey.log 2>/dev/null); dv=${dv:-0}
  if [ "$v" = "$prev" ]; then same=$((same+1)); else same=0; good=$((good+1)); fi
  prev=$v
  [ $cool -gt 0 ] && cool=$((cool-1))
  T=""
  [ $same -ge 3 ] && [ $good -ge 15 ] && T="vopstall"
  [ "$dv" != "$prevdavey" ] && T="${T}davey"
  prevdavey=$dv
  if [ -n "$T" ] && [ $cool -eq 0 ] && [ $ndump -lt $MAXDUMP ]; then
    ndump=$((ndump+1))
    SFPID=$(pgrep -x surfaceflinger | head -1)
    APP=$(pgrep -f daijishou | head -1)
    echo "TRIGGER $ndump $T up=$up app=$APP same=$same" >> $D/status
    snap "s${ndump}"
    atrace --async_dump -o $D/t${ndump}.trace >/dev/null 2>&1
    echo "DONE $ndump up=$(cut -d' ' -f1 /proc/uptime)" >> $D/status
    cool=200; same=0; good=0
  fi
  sleep 0.1
done
