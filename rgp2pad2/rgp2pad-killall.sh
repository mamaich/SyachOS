#!/system/bin/sh
# Закрывает посторонние приложения по двойному аккорду Select+Start.
#
# Логика перенесена из оригинального /vendor/bin/rgp2pad, где она была одной
# длинной строкой внутри system(). Смысл: уйти на домашний экран, затем
# остановить всё пользовательское, кроме оболочки и системных служб.
#
# Список исключений намеренно оставлен как у автора порта.

KEEP='systemui|inputmethod|ext.services|process.acore|process.media|providers.|lineageos|protonaosp|daijishou|launcher|home$|storageresize'

log() { echo "rgp2pad2: $*" > /dev/kmsg; }

input keyevent 3          # KEYCODE_HOME
sleep 0.5

PIDS=$(ps -A -o PID,UID,NAME | awk -v keep="$KEEP" 'NR>1 && $2>=10000 && $3 !~ keep {print $1}')

PKGS=""
for p in $PIDS; do
    pkg=$(cat /proc/$p/cmdline 2>/dev/null | tr '\0' '\n' | head -n1 | sed 's/:.*//')
    if [ -n "$pkg" ]; then
        case " $PKGS " in
            *" $pkg "*) ;;      # уже останавливали
            *)
                PKGS="$PKGS $pkg"
                cmd activity force-stop "$pkg" && log "force-stop $pkg"
                ;;
        esac
    else
        kill -9 "$p" 2>/dev/null && log "kill9 $p (без пакета)"
    fi
done
