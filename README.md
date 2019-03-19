# pi-setup
Setup Raspberry Pi's

This just works on Mac for now.  Happy to do Windows and Linux when I have the chance.

WARNING:  Only do this at home on a secure network.  This is by no means production ready. 

# Getting Started

Download image from <URL> and burn onto an SD card.

## Easiest

This is the easiest method, but should only be done on your own home network.

Put card into Pi.  Wire to your network (ethernet cable). Boot.

Go to http://klot-io.local/ (might take a minute to appear). 

Login with 'kloudofthings'

Set a new password. This'll be both for the interface you're using and the pi account on the Pi.

Set your network options.  This is where you can switch to wireless if you want. 

Set your cluster name and for the first one, set as master. 

Click Config.  You should have to log in with your new password. 

Watch your Status change as the Pi comes onlnie with Kuberentes

Once enabled, wire another to the network.  It should appear in the status page. 

Give it a name and network, and click Join.  You can watch it come online the Master node's status page.

## Secure

This is a little more involved but more secure. 

Pop the SD card out after burning and pop it back in.

Type `make config` in this repo and go to http://127.0.0.1:8084 when docker compose is up.

Configure this SD card, starting with the master first.  Repeat for each worker SD card.

Put the cards in the Pi's and boot up.  After a few minutes, go to http://<cluster>-klot-io.local where <cluster> is the cluster you configured.

## Apps

Once you have a master node and a few workers, head over to Apps.

Here you can install Apps.  Or you will.  I haven't done anything yet with this.

# Build your own Firmware

Make sure you're on the same network as the Pi will be.

## base image

```
# Burn the image first then
make build
make boot
```

Pop into Pi, connecting serial cable, power on, and create a console

## enable tmpfs

Login when prompted (pi/raspberry)

```
cd /boot/klot-io/bin
./tmpfs.sh
```

Will reboot when done.

## enable wifi

This is only needed so that the Pi can download.  You don't need to do this step if you're using the the wired ethernet port.

Login when prompted (pi/raspberry)

```
cd /boot/klot-io/bin
./wifi.sh
```

Answer questions for ssid and psk. 

Will reboot when done.

## install kubernetes

Login when prompted (pi/raspberry)

```
cd /boot/klot-io/bin
./kubernetes.sh
```

Will reboot when done.

## download docker images

Login when prompted (pi/raspberry)

```
cd /boot/klot-io/bin
./images.sh
```

## install clout-io services

```
cd /boot/klot-io/bin
./klot-io.sh
```

Will install and run the config daemon and then tails its logs to make sure it's working.

The daemon sets hostname to klot-io, cange pi password to 'kloudofthings', and reset network to eth0 (if needed)

# Console

```bash
screen -S pi /dev/cu.usbserial 115200
# To exit, ctrl-a, :quit and then unplug the cable
```

Can leave console going through multiple reboots of the Pi.

To disconnect, ctrl-a, :quit, and then unplugged the cable from the Mac.  Not doing this may require a hard reboot of the Mac.
