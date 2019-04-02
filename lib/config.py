import os
import time
import copy
import glob
import socket
import hashlib

import traceback

import yaml
import pykube
import urlparse
import requests
import netifaces

import avahi
import dbus
import encodings.idna

class App(pykube.objects.APIObject):

    version = "klot.io/v1"
    endpoint = "apps"
    kind = "App"

pykube.App = App


WPA = """ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=%s

network={
\tscan_ssid=1
\tssid="%s"
\t%s
}
"""

RESOURCES = {
    "Namespace": 1,
    "ServiceAccont": 2,
    "ClusterRole": 3,
    "ClusterRoleBinding": 4,
    "Role": 5,
    "RoleBinding": 6,
    "*": 7
}

SERVER = """server {

    listen       %s;
    server_name  %s;

    location / {
        proxy_pass %s://%s:%s/;
    }

}

"""


class AppException(Exception):
    pass

class Daemon(object):

    def __init__(self):

       self.config = {}
       self.mtimes = {}
       self.modified = []

       self.kube = None
       self.node = None
       self.cnames = set()

    def execute(self, command):

        print command
        os.system(command)

    def reset(self):

        print "reseting"

        self.execute("rm /boot/klot-io/reset")

        with open("/opt/klot-io/config/account.yaml", "w") as yaml_file:
            yaml.safe_dump({"password": "kloudofthings", "ssh": "disabled"}, yaml_file, default_flow_style=False)

        with open("/opt/klot-io/config/network.yaml", "w") as yaml_file:
            yaml.safe_dump({"interface": "eth0"}, yaml_file, default_flow_style=False)

        with open("/opt/klot-io/config/kubernetes.yaml", "w") as yaml_file:
            yaml.safe_dump({"role": "reset"}, yaml_file, default_flow_style=False)

    def restart(self):
        
        print "restarting"

        self.execute("cp /boot/klot-io/lib/config.py /opt/klot-io/lib/config.py")
        self.execute("chown 1000:1000 /opt/klot-io/lib/config.py")
        self.execute("chmod a+x /opt/klot-io/lib/config.py")

        self.execute("rm /boot/klot-io/lib/config.py")

        self.execute("systemctl restart klot-io-daemon")

    def reload(self):

        reloaded = False

        for yaml_path in glob.glob("/boot/klot-io/config/*.yaml"):
            self.execute("mv %s /opt/klot-io/config/" % yaml_path)
            reloaded = True

        if reloaded:
            self.execute("chown -R pi /opt/klot-io/config/")

    def load(self):

        self.modified = []

        for path in glob.glob("/opt/klot-io/config/*.yaml"):

            config = path.split("/")[-1].split('.')[0]
            mtime = os.path.getmtime(path)

            if config not in self.mtimes or self.mtimes[config] != mtime:

                with open(path, "r") as yaml_file:
                    self.config[config] = yaml.safe_load(yaml_file)

                self.mtimes[config] = mtime
                self.modified.append(config)

    def differs(self, expected, actual):

        print "actual:   %s" % actual
        print "expected: %s" % expected

        return expected != actual

    # Stolen from https://gist.github.com/gdamjan/3168336

    TTL = 15
    # Got these from /usr/include/avahi-common/defs.h
    CLASS_IN = 0x01
    TYPE_CNAME = 0x05

    @staticmethod
    def encode_cname(name):
        return '.'.join(  encodings.idna.ToASCII(p) for p in name.split('.') if p )

    @staticmethod
    def encode_rdata(name):
        def enc(part):
            a =  encodings.idna.ToASCII(part)
            return chr(len(a)), a
        return ''.join( '%s%s' % enc(p) for p in name.split('.') if p ) + '\0'

    def avahi(self):

        self.execute("systemctl restart avahi-daemon")

        if self.cnames:

            bus = dbus.SystemBus()
            server = dbus.Interface(bus.get_object(avahi.DBUS_NAME, avahi.DBUS_PATH_SERVER), avahi.DBUS_INTERFACE_SERVER)
            group = dbus.Interface(bus.get_object(avahi.DBUS_NAME, server.EntryGroupNew()), avahi.DBUS_INTERFACE_ENTRY_GROUP)

            for cname in self.cnames:
                group.AddRecord(
                    avahi.IF_UNSPEC,
                    avahi.PROTO_UNSPEC,
                    dbus.UInt32(0),
                    self.encode_cname(cname), 
                    self.CLASS_IN, 
                    self.TYPE_CNAME, 
                    self.TTL, 
                    avahi.string_to_byte_array(self.encode_rdata(server.GetHostNameFqdn()))
                )

            group.Commit()

    def account(self):

        self.execute("echo 'pi:%s' | chpasswd" % self.config["account"]["password"])

        if self.config["account"]["ssh"] == "enabled":
            self.execute("systemctl enable ssh")
            self.execute("systemctl start ssh")
        else:
            self.execute("systemctl stop ssh")
            self.execute("systemctl disable ssh")

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
            self.avahi()

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

        self.node = expected

        avahi = False

        with open("/etc/hostname", "r") as hostname_file:
            actual = hostname_file.read()

        if self.differs(expected, actual):

            with open("/etc/hostname", "w") as hostname_file:
                hostname_file.write(expected)

            self.execute("hostnamectl set-hostname %s" % expected)

            avahi = True

        with open("/etc/hosts", "r") as hosts_file:
            actual = hosts_file.readlines()[-1].split("\t")[-1].strip()

        if self.differs(expected, actual):
            self.execute("sed -i 's/127.0.1.1\t.*/127.0.1.1\t%s/' /etc/hosts" % expected)
            avahi = True

        if avahi:
            self.avahi()

    def kubernetes(self):

        if self.config["kubernetes"]["role"] == "reset":

            if not os.path.exists("/home/pi/.kube/config"):
                print "already reset kubernetes"
                return

            try:
                pykube.Node.objects(self.kube).filter().get(name=self.node).delete()
            except pykube.ObjectDoesNotExist:
                pass

            self.host("klot-io")
            self.execute("rm -f /opt/klot-io/config/kubernetes.yaml")
            self.execute("rm -f /home/pi/.kube/config")
            self.execute("kubeadm reset")
            self.execute("reboot")
 
        attempts = 20

        while attempts:

            interfaces = self.interfaces()
            print "interfaces: %s" % interfaces

            if self.config["network"]['interface'] in interfaces:
                break

            time.sleep(5)
            attempts -= 1

        ip = interfaces[self.config["network"]['interface']]
        encoded = hashlib.sha256(self.config["account"]["password"]).hexdigest()
        token = "%s.%s" % (encoded[13:19], encoded[23:39])

        if self.config["kubernetes"]["role"] == "master":

            self.host("%s-klot-io" % self.config["kubernetes"]["cluster"])

            if os.path.exists("/home/pi/.kube/config"):
                print "already initialized master"
                return

            self.execute(" ".join([
                'kubeadm',
                'init',
                '--token=%s' % token,
                '--token-ttl=0',
                '--apiserver-advertise-address=%s' % ip,
                '--pod-network-cidr=10.244.0.0/16',
                '--kubernetes-version=v1.10.2'
            ]))

            with open("/etc/kubernetes/admin.conf", "r") as config_file:
                config = yaml.safe_load(config_file)

            config["clusters"][0]["cluster"]["server"] = 'https://%s:6443' % ip
            config["clusters"][0]["name"] = self.node
            config["users"][0]["name"] = self.node
            config["contexts"][0]["name"] = self.node
            config["contexts"][0]["context"]["cluster"] = self.node
            config["contexts"][0]["context"]["user"] = self.node
            config["current-context"] = self.node

        elif self.config["kubernetes"]["role"] == "worker":

            self.host("%s-%s-klot-io" % (self.config["kubernetes"]["name"], self.config["kubernetes"]["cluster"]))

            if os.path.exists("/etc/kubernetes/bootstrap-kubelet.conf"):
                print "already initialized worker"
                return

            self.execute(" ".join([
                'kubeadm',
                'join',
                '%s:6443' % socket.gethostbyname('%s-klot-io.local' % self.config["kubernetes"]["cluster"]),
                '--token=%s' % token,
                '--discovery-token-unsafe-skip-ca-verification'
            ]))

            config = requests.get(
                'http://%s-klot-io.local/api/kubectl' % self.config["kubernetes"]["cluster"],
                headers={"klot-io-password": self.config["account"]['password']},
            ).json()["kubectl"]

        self.execute("mkdir -p /home/pi/.kube")
        self.execute("rm -f /home/pi/.kube/config")
        
        with open("/home/pi/.kube/config", "w") as config_file:
            yaml.safe_dump(config, config_file, default_flow_style=False)

        self.execute("chown pi:pi /home/pi/.kube/config")

        if self.config["kubernetes"]["role"] == "master":
            self.execute("sudo -u pi -- kubectl apply -f /opt/klot-io/kubernetes/kube-flannel.yml")
            self.execute("sudo -u pi -- kubectl apply -f /opt/klot-io/kubernetes/klot-io-app-crd.yaml")

    def resources(self, obj):

        resources = []

        for manifest in obj["spec"]["manifests"]:

            source = copy.deepcopy(obj["spec"]["source"])
            source.update(manifest)

            print "parsing %s" % source

            if "url" in source:

                url = source["url"]

            elif "site" in source and source["site"] == "github.com":

                if "repo" not in source:
                    raise AppException("missing source.repo for %s" % source["site"])

                repo = source["repo"]
                version = source["version"] if "version" in source else "master"
                path = source["path"] if "path" in source else "klot-io-app.yaml"

                url = "https://raw.githubusercontent.com/%s/%s/%s" % (repo, version, path)

            else:

                raise AppException("cannot parse %s" % source)

            print "fetching %s" % url

            response = requests.get(url)

            if response.status_code != 200:
                raise AppException("%s error from %s: %s" % (response.status_code, url, response.text))

            resources.extend(list(yaml.safe_load_all(response.text)))

        resources.sort(key= lambda resource: RESOURCES[resource["kind"]] if resource["kind"] in RESOURCES else RESOURCES["*"])

        return resources

    def display(self, obj):

        display = [obj["kind"]]

        if "namespace" in obj["metadata"]:
            display.append(obj["metadata"]["namespace"])

        display.append(obj["metadata"]["name"])

        return "/".join(display)

    def apps(self):

        for obj in [app.obj for app in pykube.App.objects(self.kube).filter()]:

            try:

                if "status" not in obj:

                    print "fetching resources for %s" % self.display(obj)
                    obj["resources"] = self.resources(obj)
                    obj["status"] = "Ready"

                elif obj["status"] == "Install":

                    print "installing %s" % self.display(obj)
                    for resource in obj["resources"]:
                        print "creating %s" % self.display(resource)
                        getattr(pykube, resource["kind"])(self.kube, resource).create()
                    if "settings" in obj["spec"]:
                        obj["settings"] = obj["spec"]["settings"]
                    obj["status"] = "Installed"

                elif obj["status"] == "Uninstall":

                    print "unininstalling %s" % self.display(obj)
                    for resource in reversed(obj["resources"]):
                        print "deleting %s" % self.display(resource)
                        getattr(pykube, resource["kind"])(self.kube, resource).delete()
                    if "settings" in obj:
                        del obj["settings"]
                    obj["status"] = "Ready"

            except Exception as exception:

                obj["status"] = "Error"
                obj["error"] = str(exception)
                traceback.print_exc()

            pykube.App(self.kube, obj).replace()

    def nginx(self, expected):

        actual = {}

        for nginx_path in glob.glob("/etc/nginx/conf.d/*.conf"):

            host = nginx_path.split("/")[-1].split(".conf")[0]
            actual[host] = {"servers": []}

            with open(nginx_path, "r") as nginx_file:
                for nginx_line in nginx_file:
                    if "proxy_pass" in nginx_line:
                        actual[host]["servers"].append({
                            "protocol": nginx_line.split(":")[0].split(" ")[-1],
                            "port": int(nginx_line.split(":")[-1].split("/")[0])
                        })
                        actual[host]["ip"] = nginx_line.split("/")[2].split(":")[0]

        if expected != actual:
        
            self.differs(expected, actual)
            self.execute("rm -f /etc/nginx/conf.d/*.conf")

            for host in expected:
                with open("/etc/nginx/conf.d/%s.conf" % host, "w") as nginx_file:
                    for server in expected[host]["servers"]:
                        nginx_file.write(SERVER % (server["port"], host, server["protocol"], expected[host]["ip"], server["port"]))

            self.execute("systemctl restart nginx")

    def services(self):

        nginx = {}
        cnames = set()

        for service in [service.obj for service in pykube.Service.objects(self.kube).filter(namespace=pykube.all)]:

            if (
                "type" not in service["spec"] or service["spec"]["type"] != "LoadBalancer" or 
                "ports" not in service["spec"] or "selector" not in service["spec"] or 
                "namespace" not in service["metadata"]
            ):
                continue

            servers = []

            for port in service["spec"]["ports"]:

                if "name" not in port:
                    continue

                if port["name"].lower().startswith("https"):
                    servers.append({
                        "protocol": "https",
                        "port": port["port"]
                    })
                elif port["name"].lower().startswith("http"):
                    servers.append({
                        "protocol": "http",
                        "port": port["port"]
                    })

            if not servers:
                continue

            node_ips = {}

            for pod in [pod.obj for pod in pykube.Pod.objects(self.kube).filter(
                namespace=service["metadata"]["namespace"], 
                selector=service["spec"]["selector"]
            )]:
                if "nodeName" in pod["spec"] and "podIP" in pod["status"]:
                    node_ips[pod["spec"]["nodeName"]] = pod["status"]["podIP"]

            if not node_ips or sorted(node_ips.keys())[0] != self.node:
                continue

            ip = node_ips[self.node]

            host = ("%s.%s.%s-klot-io.local" % (
                service["metadata"]["name"],
                service["metadata"]["namespace"],
                self.config["kubernetes"]["cluster"]
            ))

            cnames.add(host)
            nginx[host] = {
                "ip": ip,
                "servers": servers
            }

        if cnames != self.cnames:
            self.differs(cnames, self.cnames)
            self.cnames = cnames
            self.avahi()

        self.nginx(nginx)

    def clean(self):

        past = time.time() - 60

        for tmp_file in glob.glob("/tmp/tmp??????"):
            if past > os.path.getmtime(tmp_file):
                os.remove(tmp_file)

    def process(self):

        if os.path.exists("/boot/klot-io/reset"):
            self.reset()

        if os.path.exists("/boot/klot-io/lib/config.py"):
            self.restart()

        self.reload()
        self.load()

        if "account" in self.modified:
            self.account()

        if "network" in self.modified:
            self.network()

        if "kubernetes" in self.modified:
            self.kubernetes()

        if not self.kube and os.path.exists("/home/pi/.kube/config"):
            self.kube = pykube.HTTPClient(pykube.KubeConfig.from_file("/home/pi/.kube/config"))

        if self.kube:

            if self.config["kubernetes"]["role"] == "master":
                self.apps()

            self.services()
            self.clean()

    def run(self):

        while True:

            try:

                self.process()

            except Exception as exception:

                traceback.print_exc()

            time.sleep(5)
