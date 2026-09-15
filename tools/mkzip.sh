set -e
cd /mnt/t/Dump/RG52Mini/android
# Образ можно указать аргументом; по умолчанию — базовый.
N=${1:-SyachOS-RG52Mini-V1.0.317m4.0.img}
echo "образ: $(stat -c %s $N) байт"
sha256sum $N > $N.sha256
cat $N.sha256
rm -f $N.zip
zip -1 $N.zip $N > /dev/null
echo "архив собран, проверяю:"
unzip -t $N.zip 2>&1 | tail -2
ls -la $N $N.zip $N.sha256
