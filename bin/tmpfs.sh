#!/bin/sh

set -e

echo "changing logrotate to daily"
sudo sed -i -E 's/weekly|monthly|yearly/daily/g' /etc/logrotate.conf
sudo sed -i -E 's/rotate [0-9]+/rotate 0/g' /etc/logrotate.conf
sudo sed -i -E 's/weekly|monthly|yearly/daily/g' /etc/logrotate.d/*
sudo sed -i -E 's/rotate [0-9]+/rotate 0/g' /etc/logrotate.d/*

echo "enabling tmpfs"
sudo cat <<EOT | sudo tee -a /etc/fstab

tmpfs    /tmp    tmpfs    defaults,noatime,nosuid,size=20m    0 0
tmpfs    /var/tmp    tmpfs    defaults,noatime,nosuid,size=20m    0 0
tmpfs    /var/log    tmpfs    defaults,noatime,nosuid,mode=0755,size=20m    0 0
tmpfs    /var/log/nginx    tmpfs    defaults,noatime,nosuid,mode=0755,size=10m    0 0
tmpfs    /var/spool/mqueue    tmpfs    defaults,noatime,nosuid,mode=0700,gid=12,size=5m    0 0
EOT

echo "disabling swap"
sudo dphys-swapfile swapoff && \
  sudo dphys-swapfile uninstall && \
  sudo update-rc.d dphys-swapfile remove

sudo reboot