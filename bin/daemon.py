#!/usr/bin/env python

import os
import time
import glob
import yaml
import netifaces
import traceback

WPA = """ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=%s

network={
\tscan_ssid=1
\tssid="%s"
\t%s
}
"""

class Daemon(object):

    def __init__(self):

       self.config = {}
       self.mtimes = {}
       self.modified = []

    def execute(self, command):

        print command
        os.system(command)

    def reset(self):

        if not os.path.exists("/boot/clot-io/reset"):
            return

        self.execute("echo 'pi:cloudofthings' | chpasswd")

        self.execute("hostnamectl set-hostname clot-io")
        self.execute("sed -i 's/127.0.1.1\t.*/127.0.1.1\tclot-io/' /etc/hosts")

        os.system("sed -i 's/allow-interfaces=.*/allow-interfaces=eth0/' /etc/avahi/avahi-daemon.conf" % expected)
        self.execute("service avahi-daemon restart")

        with open("/etc/wpa_supplicant/wpa_supplicant.conf", "w") as wpa_file:
            wpa_file.write(WPA % ("NOPE", "nope", 'key_mgmt=NONE'))

        self.execute("wpa_cli -i wlan0 reconfigure")
        self.execute("rm /boot/clot-io/reset")

    def restart(self):
        
        if not os.path.exists("/boot/clot-io/bin/daemon.py"):
            return

        print "restarting"

        self.execute("cp /boot/clot-io/bin/daemon.py /opt/clot-io/bin/daemon.py")
        self.execute("chown 1000:1000 /opt/clot-io/bin/daemon.py")
        self.execute("chmod a+x /opt/clot-io/bin/daemon.py")

        self.execute("rm /boot/clot-io/bin/daemon.py")

        self.execute("systemctl restart clot-io-daemon")

    def reload(self):

        reloaded = False

        for yaml_path in glob.glob("/boot/clot-io/config/*.yaml"):
            self.execute("mv %s /opt/clot-io/config/" % yaml_path)
            reloaded = True

        if reloaded:
            self.execute("chown -R pi /opt/clot-io/config/")

    def load(self):

        self.modified = []

        for path in glob.glob("/opt/clot-io/config/*.yaml"):

            config = path.split("/")[-1].split('.')[0]
            mtime = os.path.getmtime(path)

            if config not in self.mtimes or self.mtimes[config] != mtime:

                with open(path, "r") as yaml_file:
                    self.config[config] = yaml.load(yaml_file)

                self.mtimes[config] = mtime
                self.modified.append(config)

    def differs(self, expected, actual):

        print "actual:   %s" % actual
        print "expected: %s" % expected

        return expected != actual

    def account(self):

        if "account" not in self.modified:
            return

        self.execute("echo 'pi:%s' | chpasswd" % self.config["account"]["password"])

    def network(self):

        if "network" not in self.modified:
            return

        expected = self.config["network"]['interface']

        with open("/etc/avahi/avahi-daemon.conf", "r") as avahi_file:
            for avahi_line in avahi_file:
                if "allow-interfaces" in avahi_line:
                    actual = avahi_line.split('=')[-1].strip()

        if self.differs(expected, actual):

            os.system("sed -i 's/allow-interfaces=.*/allow-interfaces=%s/' /etc/avahi/avahi-daemon.conf" % expected)
            self.execute("service avahi-daemon restart")

        if expected == "eth0":

            self.execute("sudo ifconfig wlan0 down")

            expected = WPA % ("NOPE", "nope", 'key_mgmt=NONE')

        elif expected == "wlan0":

            self.execute("sudo ifconfig wlan0 up")

            expected = WPA % (
                self.config["network"]["country"],
                self.config["network"]["ssid"],
                'psk="%s"' % self.config["network"]["psk"] if self.config["network"]["psk"] else 'key_mgmt=NONE'
            )

        with open("/etc/wpa_supplicant/wpa_supplicant.conf", "r") as wpa_file:
            actual = wpa_file.read()

        if self.differs(expected, actual):

            with open("/etc/wpa_supplicant/wpa_supplicant.conf", "w") as wpa_file:
                wpa_file.write(expected)

            self.execute("wpa_cli -i wlan0 reconfigure")

    def interfaces(self):

        interfaces = {}
        for interface in netifaces.interfaces():

            ifaddresses = netifaces.ifaddresses(interface)

            if netifaces.AF_INET in ifaddresses:
                interfaces[interface] = ifaddresses[netifaces.AF_INET][0]['addr']

        return interfaces

    def host(self, expected):

        with open("/etc/hostname", "r") as hostname_file:
            actual = hostname_file.read()

        if self.differs(expected, actual):

            with open("/etc/hostname", "w") as hostname_file:
                hostname = hostname_file.write(expected)

            self.execute("hostnamectl set-hostname %s" % expected)

        with open("/etc/hosts", "r") as hosts_file:
            actual = hosts_file.readlines()[-1].split("\t")[-1].strip()

        if self.differs(expected, actual):
            self.execute("sed -i 's/127.0.1.1\t.*/127.0.1.1\t%s/' /etc/hosts" % expected)

    def k8s(self):

        if "k8s" not in self.modified:
            return

        if self.config["k8s"]["role"] == "reset":
            self.execute("kubeadm reset")
            self.execute("rm /opt/clot-io/config/k8s.yaml")
            self.execute("reboot")

        interfaces = self.interfaces()

        print "interfaces: %s" % interfaces

        if self.config["network"]['interface'] not in interfaces:
            return

        ip = interfaces[self.config["network"]['interface']]
        domain = '%s-clot-io.local' % self.config["k8s"]["cluster"]

        if self.config["k8s"]["role"] == "master":

            self.host(domain)

            self.execute(" ".join([
                'kubeadm',
                'init',
                '--token=%s' % self.config["k8s"]["token"],
                '--token-ttl=0',
                '--apiserver-advertise-address=%s' % ip,
                '--kubernetes-version=v1.10.2'
            ]))

            self.execute("mkdir -p /home/pi/.kube")
            self.execute("rm -f /home/pi/.kube/config")
            
            with open("/etc/kubernetes/admin.conf", "r") as config_file:
                config = yaml.load(config_file)

            config["clusters"][0]["cluster"]["server"] = 'https://%s:6443' % ip
            config["clusters"][0]["name"] = self.config["k8s"]["cluster"]
            config["users"][0]["name"] = self.config["k8s"]["cluster"]
            config["contexts"][0]["name"] = self.config["k8s"]["cluster"]
            config["contexts"][0]["context"]["cluster"] = self.config["k8s"]["cluster"]
            config["contexts"][0]["context"]["user"] = self.config["k8s"]["cluster"]
            config["current-context"] = self.config["k8s"]["cluster"]

            with open("/home/pi/.kube/config", "w") as config_file:
                yaml.dump(config, config_file, default_flow_style=False)

            self.execute("chown pi:pi /home/pi/.kube/config")
            self.execute("sudo -u pi -- kubectl apply -f /opt/clot-io/config/kube-flannel.yml")

        elif self.config["k8s"]["role"] == "worker":

            self.host("%s-%s" (self.config["k8s"]["name"], domain))

            self.execute(" ".join([
                'kubeadm',
                'join',
                '%s:6443' % socket.gethostbyname(domain),
                '--token=%s' % self.config["k8s"]["token"],
                '--discovery-token-unsafe-skip-ca-verification'
            ]))

    def process(self):

        self.reset()
        self.restart()
        self.reload()

        self.load()
        self.account()
        self.network()
        self.k8s()

    def run(self):

        while True:

            try:

                self.process()

            except Exception as exception:

                traceback.print_exc()

            time.sleep(5)

if __name__ == '__main__':
    
    Daemon().run()