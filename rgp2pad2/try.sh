#!/system/bin/sh
# Подмена штатного демона на нашу замену — без правки образа.
#
#   try.sh on    остановить /vendor/bin/rgp2pad, запустить /data/local/tmp/rgp2pad2
#   try.sh off   вернуть штатный
#   try.sh state показать, кто сейчас работает
#
# Одновременно они работать не могут: оба делают EVIOCGRAB на одном геймпаде.

T=/data/local/tmp
PIDFILE=$T/rgp2pad2.pid

running() {            # pid нашей замены, если жива
    [ -f "$PIDFILE" ] || return 1
    p=$(cat "$PIDFILE")
    [ -n "$p" ] && [ -d "/proc/$p" ] || return 1
    echo "$p"
}

state() {
    p=$(running) && echo "  замена: работает, pid $p" || echo "  замена: не работает"
    echo "  штатный: $(getprop init.svc.rgp2pad)"
    echo "  устройства ввода:"
    for d in /dev/input/event*; do
        n=$(cat /sys/class/input/$(basename $d)/device/name 2>/dev/null)
        case "$n" in *mouse*|*Xbox*|*joypad*) echo "    $d = $n";; esac
    done
}

case "$1" in
on)
    p=$(running) && { echo "уже работает, pid $p"; exit 0; }
    [ -x $T/rgp2pad2 ] || { echo "нет $T/rgp2pad2"; exit 1; }
    setprop ctl.stop rgp2pad
    sleep 1
    setsid $T/rgp2pad2 </dev/null >/dev/null 2>&1 &
    echo $! > "$PIDFILE"
    sleep 2
    echo "включена замена"
    state
    ;;
off)
    p=$(running) && kill "$p" 2>/dev/null
    rm -f "$PIDFILE"
    sleep 1
    setprop ctl.start rgp2pad
    sleep 2
    echo "возвращён штатный"
    state
    ;;
state|"")
    state
    ;;
*)
    echo "использование: try.sh on|off|state"
    exit 1
    ;;
esac
