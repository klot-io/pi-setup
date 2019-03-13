#!/usr/bin/env bash

set -e

echo "ssid: "
read SSID

echo "psk: "
read PSK

echo "updating wpa"
if [ -z "$PSK" ]
then

sudo cat <<EOT | sudo tee /etc/wpa_supplicant/wpa_supplicant.conf
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={
        ssid="$SSID"
        key_mgmt=NONE
        scan_ssid=1
}
EOT

else

sudo cat <<EOT | sudo tee /etc/wpa_supplicant/wpa_supplicant.conf
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={
        ssid="$SSID"
        psk="$PSK"
        scan_ssid=1
}
EOT

fi

echo "updating avahi"
sudo sed -i 's/#allow-interfaces=eth0/allow-interfaces=wlan0/' /etc/avahi/avahi-daemon.conf

sudo reboot