#!/bin/sh

set -e

echo "setting account password"
echo 'pi:kloudofthings' | sudo chpasswd

echo "setting hostname to klot-io"
sudo sed -i s/raspberrypi/klot-io/g /etc/hosts
sudo hostnamectl --transient set-hostname klot-io
sudo hostnamectl --static set-hostname klot-io
sudo hostnamectl --pretty set-hostname klot-io
sudo service avahi-daemon restart

echo "installing klot-io requirements"
sudo apt-get update
sudo apt-get install -y git python-pip gcc python-dev libsystemd-dev python-avahi
sudo mkdir -p /opt/klot-io/
sudo cp /boot/klot-io/requirements.txt /opt/klot-io/requirements.txt
sudo pip install requests==2.21
sudo pip install -r /opt/klot-io/requirements.txt
sudo mkdir -p /opt/klot-io/lib/
sudo mkdir -p /opt/klot-io/bin/

echo "install config files"
sudo mkdir -p /opt/klot-io/config/
sudo cp /boot/klot-io/config/account.yaml /opt/klot-io/config/
sudo cp /boot/klot-io/config/network.yaml /opt/klot-io/config/

echo "install kubernetes files"
sudo mkdir -p /opt/klot-io/kubernetes/
sudo cp /boot/klot-io/kubernetes/kube-flannel.yml /opt/klot-io/kubernetes/
sudo cp /boot/klot-io/kubernetes/klot-io-app-crd.yaml /opt/klot-io/kubernetes/

echo "installing klot-io dns"
sudo cp /boot/klot-io/lib/name.py /opt/klot-io/lib/
sudo cp /boot/klot-io/bin/dns.py /opt/klot-io/bin/
sudo cp /boot/klot-io/service/klot-io-dns.service /etc/systemd/system/

echo "installing klot-io daemon"
sudo cp /boot/klot-io/lib/config.py /opt/klot-io/lib/
sudo cp /boot/klot-io/bin/k3s.sh /opt/klot-io/bin/
sudo cp /boot/klot-io/bin/daemon.py /opt/klot-io/bin/
sudo cp /boot/klot-io/service/klot-io-daemon.service /etc/systemd/system/

echo "installing klot-io api"
sudo cp /boot/klot-io/lib/manage.py /opt/klot-io/lib/
sudo cp /boot/klot-io/bin/api.py /opt/klot-io/bin/
sudo cp /boot/klot-io/service/klot-io-api.service /etc/systemd/system/

echo "installing klot-io gui"
sudo apt install -y nginx
sudo cp /boot/klot-io/etc/nginx.conf /etc/nginx/
sudo cp /boot/klot-io/etc/rpi.conf /etc/nginx/sites-available/default
sudo cp -r /boot/klot-io/www /opt/klot-io/www

echo "setting permissions"
sudo chmod a+x -R /opt/klot-io/bin
sudo chown -R 1000:1000 /opt/klot-io

echo "starting dns"
sudo systemctl enable klot-io-dns
sudo systemctl start klot-io-dns
sleep 5
echo "verify DNS recursive pass thru - q to exit"
host klot.io 127.0.0.1
sudo journalctl -u klot-io-dns

echo "starting daemon"
sudo systemctl enable klot-io-daemon
sudo systemctl start klot-io-daemon
sleep 10
echo "verify password change and network change (if applicable) - q to exit"
sudo journalctl -u klot-io-daemon

echo "starting api"
sudo systemctl enable klot-io-api
sudo systemctl start klot-io-api
echo "hit http://klot-io.local:8083/health - hit return to continue - q to exit"
read API
sudo journalctl -u klot-io-api

echo "starting gui"
sudo systemctl enable nginx
sudo systemctl reload nginx
echo "hit http://klot-io.local/ - hit return to continue - q to exit"
read GUI
sudo journalctl -u nginx
