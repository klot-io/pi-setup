# pi-setup
Setup Raspberry Pi's

# Console

```bash
screen -S pi /dev/cu.usbserial 115200
# To exit, ctrl-a, :quit and then unplug the cable
```

Can leave console going through multiple reboots.

# Firmware

## base image

```
# Burn the image
make build
make boot
```

Pop into Pi, connecting serial cable, power on, and create a console

## enable tmpfs

Login when prompted (pi/raspberry)

```
cd /boot/clot-io/bin
./tmpfs.sh
```

Will reboot when done.

## enabled wifi (optional, not needed if wired)

Login when prompted (pi/raspberry)

```
cd /boot/clot-io/bin
./wifi.sh
```

Answer questions for ssid and psk. 

Will reboot when done.

## install kubernetes

Login when prompted (pi/raspberry)

```
cd /boot/clot-io/bin
./kubernetes.sh
```

Will reboot when done.

## download docker images

Login when prompted (pi/raspberry)

```
cd /boot/clot-io/bin
./images.sh
```

## install clout-io services

```
cd /boot/clot-io/bin
./clot-io.sh
```

Will set hostname to clot-io, cange pi password to 'cloudofthings', and reset network to eth0 (if needed)