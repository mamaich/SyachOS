#!/bin/bash
# Собирает RRO-оверлей, который делает SBC кодеком A2DP по умолчанию.
#
# Приоритеты кодеков приложение Bluetooth берёт из своих ресурсов, системного
# свойства для них нет, поэтому единственный чистый путь - оверлей.
# Штатные значения: SBC 1001, AAC 2001, aptX 3001, aptX HD 4001, LDAC 5001.
# Понижаем AAC до 500: SBC выигрывает автоматически, AAC остаётся доступным
# для ручного выбора в меню разработчика.
#
# android:isStatic="true" - так объявлены все штатные оверлеи этой прошивки,
# именно это включает их без файла конфигурации и без записи в /data
# (то есть переживает и перепрошивку).
set -e
A=/mnt/t/Dump/RG52Mini/android
S=$A/parts/p4_system.img
BT=~/rg52/sdk/build-tools
W=~/rg52/overlay; rm -rf $W; mkdir -p $W/res/values out
cd $W; mkdir -p out

debugfs -R "dump /system/framework/framework-res.apk $W/framework-res.apk" $S >/dev/null 2>&1

cat > AndroidManifest.xml <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="org.rg52mini.bluetooth.codec.overlay">
    <application android:hasCode="false" />
    <overlay
        android:targetPackage="com.android.bluetooth"
        android:priority="100"
        android:isStatic="true" />
</manifest>
XML

cat > res/values/config.xml <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <integer name="a2dp_source_codec_priority_aac">500</integer>
</resources>
XML

$BT/aapt2 compile --dir res -o out/res.zip
$BT/aapt2 link -o out/unsigned.apk --manifest AndroidManifest.xml \
    -I framework-res.apk --min-sdk-version 33 --target-sdk-version 33 out/res.zip
[ -f key.jks ] || keytool -genkeypair -keystore key.jks -storepass android -keypass android \
    -alias ovl -keyalg RSA -keysize 2048 -validity 10950 -dname "CN=RG52Mini Overlay" 2>/dev/null
$BT/zipalign -f 4 out/unsigned.apk out/aligned.apk
$BT/apksigner sign --ks key.jks --ks-pass pass:android --key-pass pass:android \
    --out $A/RG52MiniBtCodecOverlay.apk out/aligned.apk
$BT/apksigner verify $A/RG52MiniBtCodecOverlay.apk && echo "подпись в порядке"
$BT/aapt2 dump xmltree $A/RG52MiniBtCodecOverlay.apk --file AndroidManifest.xml | grep -E 'isStatic|targetPackage|priority'
$BT/aapt2 dump resources $A/RG52MiniBtCodecOverlay.apk | grep -A1 a2dp
ls -la $A/RG52MiniBtCodecOverlay.apk
