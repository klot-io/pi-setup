#!/bin/sh

set -e

echo "enabling ssh"
sudo systemctl enable ssh

echo "setting hostname to clot-io"
sudo sed -i s/raspberrypi/clot-io/g /etc/hosts
sudo hostnamectl --transient set-hostname clot-io
sudo hostnamectl --static set-hostname clot-io
sudo hostnamectl --pretty set-hostname clot-io

echo "installing clot-io requirements"
sudo apt-get install -y python-pip
sudo mkdir -p /opt/clot-io/
sudo cp /boot/clot-io/requirements.txt /opt/clot-io/requirements.txt
sudo pip install -r /opt/clot-io/requirements.txt

echo "installing clot-io daemon"
sudo mkdir -p /opt/clot-io/bin/
sudo mkdir -p /opt/clot-io/config/
sudo cp /boot/clot-io/bin/daemon.py /opt/clot-io/bin/
sudo chmod a+x -R /opt/clot-io/bin/
sudo chown -R 1000:1000 /opt/clot-io
sudo cp /boot/clot-io/service/clot-io-daemon.service /etc/systemd/system/
sudo systemctl enable clot-io-daemon
sudo systemctl start clot-io-daemon
sudo journalctl -u clot-io-daemon.service -f