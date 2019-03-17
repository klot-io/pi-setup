#!/bin/bash

set -e

echo "exporting image"

VERSION=$1

DEVICEPATH=/dev/$(diskutil list | grep FDisk_partition_scheme | awk '{ print $5 }')

sudo dd if=${DEVICEPATH} of=./images/pi-$VERSION.img bs=4m & pid=$!
while sudo kill -0 $pid 2> /dev/null; do
    sudo kill -s INFO $pid
    sleep 5
done
sudo chown "$USER" ./images/pi-$VERSION.img
