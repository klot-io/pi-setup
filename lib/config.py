import os
import time
import copy
import glob
import hashlib

import traceback

import yaml
import pykube
import requests
import netifaces

import dbus
import encodings.idna


WPA = """ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=%s

network={
\tscan_ssid=1
\tssid="%s"
\t%s
}
"""

RESOURCES = [
    "Namespace",
    "ConfigMap",
    "Secret",
    "ServiceAccount",
    "ClusterRole",
    "ClusterRoleBinding",
    "Role",
    "RoleBinding"
]

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

        print(command)
        os.system(command)

    def reset(self):

        print("reseting")

        self.execute("rm /boot/klot-io/reset")

        with open("/opt/klot-io/config/account.yaml", "w") as yaml_file:
            yaml.safe_dump({"password": "kloudofthings", "ssh": "disabled"}, yaml_file, default_flow_style=False)

        with open("/opt/klot-io/config/network.yaml", "w") as yaml_file:
            yaml.safe_dump({"interface": "eth0"}, yaml_file, default_flow_style=False)

        with open("/opt/klot-io/config/kubernetes.yaml", "w") as yaml_file:
            yaml.safe_dump({"role": "reset"}, yaml_file, default_flow_style=False)

    def restart(self):

        print("restarting")

        self.execute("cp /boot/klot-io/lib/config.py /opt/klot-io/lib/config.py")
        self.execute("chown 1000:1000 /opt/klot-io/lib/config.py")
        self.execute("chmod a+x /opt/klot-io/lib/config.py")

        self.execute("rm /boot/klot-io/lib/config.py")

        self.execute("systemctl restart klot-io-daemon")

    def reload(self):

        reloaded = False

        for yaml_path in glob.glob("/boot/klot-io/config/*.yaml"):
            self.execute(f"mv {yaml_path} /opt/klot-io/config/")
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

        print(f"actual:   {actual}")
        print(f"expected: {expected}")

        return expected != actual

    def uninitialized(self):

        expected = os.path.exists("/opt/klot-io/config/uninitialized")

        try:

            requests.get("http://klot-io.local/api/status", timeout=5)
            actual = True

        except:

            actual = False

        if expected and not actual:
            print("uninitialized not found")
            os.remove("/opt/klot-io/config/uninitialized")
        elif not expected and actual:
            print("uninitialized found")
            open("/opt/klot-io/config/uninitialized", "w").close()

    # Stolen from https://gist.github.com/gdamjan/3168336

    TTL = 15
    # Got these from /usr/include/avahi-common/defs.h
    CLASS_IN = 0x01
    TYPE_CNAME = 0x05

    # Got these from these from the avahi module
    PROTO_UNSPEC = -1
    IF_UNSPEC = -1

    DBUS_NAME = "org.freedesktop.Avahi"
    DBUS_INTERFACE_SERVER = DBUS_NAME + ".Server"
    DBUS_PATH_SERVER = "/"
    DBUS_INTERFACE_ENTRY_GROUP = DBUS_NAME + ".EntryGroup"

    @staticmethod
    def encode_cname(name):
        return '.'.join(  encodings.idna.ToASCII(p).decode('utf-8') for p in name.split('.') if p )

    @staticmethod
    def encode_rdata(name):
        def enc(part):
            a =  encodings.idna.ToASCII(part).decode('utf-8')
            return chr(len(a)), a
        return ''.join( '%s%s' % enc(p) for p in name.split('.') if p ) + '\0'

    @staticmethod
    def string_to_byte_array(s):
        r = []

        for c in s:
            r.append(dbus.Byte(ord(c)))

        return r

    def avahi(self):

        self.execute("systemctl restart avahi-daemon")

        if self.cnames:

            bus = dbus.SystemBus()
            server = dbus.Interface(bus.get_object(self.DBUS_NAME, self.DBUS_PATH_SERVER), self.DBUS_INTERFACE_SERVER)
            group = dbus.Interface(bus.get_object(self.DBUS_NAME, server.EntryGroupNew()), self.DBUS_INTERFACE_ENTRY_GROUP)

            for cname in self.cnames:
                group.AddRecord(
                    self.IF_UNSPEC,
                    self.PROTO_UNSPEC,
                    dbus.UInt32(0),
                    self.encode_cname(cname),
                    self.CLASS_IN,
                    self.TYPE_CNAME,
                    self.TTL,
                    self.string_to_byte_array(self.encode_rdata(server.GetHostNameFqdn()))
                )

            group.Commit()

    def account(self):

        self.execute(f"echo 'pi:{self.config['account']['password']}' | chpasswd")

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

            os.system(f"sed -i 's/allow-interfaces=.*/allow-interfaces={expected}/' /etc/avahi/avahi-daemon.conf")
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

            self.execute(f"hostnamectl set-hostname {expected}")

            avahi = True

        with open("/etc/hosts", "r") as hosts_file:
            actual = hosts_file.readlines()[-1].split("\t")[-1].strip()

        if self.differs(expected, actual):
            self.execute(f"sed -i 's/127.0.1.1\t.*/127.0.1.1\t{expected}/' /etc/hosts")
            avahi = True

        if avahi:
            self.avahi()

    def kubernetes(self):

        if self.config["kubernetes"]["role"] == "reset":

            if (
                not os.path.exists("/etc/rancher/k3s") and
                not os.path.exists("/var/lib/rancher/k3s") and
                not os.path.exists("/home/pi/.kube/config")
            ):
                print("already reset kubernetes")
                return

            try:
                pykube.Node.objects(self.kube).get(name=self.node).delete()
            except pykube.ObjectDoesNotExist:
                print(f"node {self.node} not found")
            except Exception:
                traceback.print_exc()

            if os.path.exists("/usr/local/bin/k3s-uninstall.sh"):
                self.execute("/usr/local/bin/k3s-uninstall.sh")
            elif os.path.exists("/usr/local/bin/k3s-agent-uninstall.sh"):
                self.execute("/usr/local/bin/k3s-agent-uninstall.sh")

            self.execute("rm -f /home/pi/.kube/config")
            self.execute("rm -f /opt/klot-io/config/kubernetes.yaml")

            self.host("klot-io")

            self.kube = None

            return

        elif self.config["kubernetes"]["role"] == "master":

            self.host(f"{self.config['kubernetes']['cluster']}-klot-io")

        elif self.config["kubernetes"]["role"] == "worker":

            self.host(f"{self.config['kubernetes']['name']}-{self.config['kubernetes']['cluster']}-klot-io")

        if os.path.exists("/home/pi/.kube/config"):
            print("already initialized")
            return

        attempts = 20

        while attempts:

            interfaces = self.interfaces()
            print(f"interfaces: {interfaces}")

            if self.config["network"]['interface'] in interfaces:
                break

            time.sleep(5)
            attempts -= 1

        if self.config["kubernetes"]["role"] == "master":

            ip = interfaces[self.config["network"]['interface']]

            self.execute(" ".join([
                'INSTALL_K3S_VERSION=v0.9.1',
                f'K3S_CLUSTER_SECRET={self.config["account"]["password"]}',
                'INSTALL_K3S_EXEC="--no-deploy=traefik --no-deploy=servicelb --write-kubeconfig-mode=644"',
                '/opt/klot-io/bin/k3s.sh',
                'server'
            ]))

            with open("/etc/rancher/k3s/k3s.yaml", "r") as config_file:
                config = yaml.safe_load(config_file)

            config["clusters"][0]["cluster"]["server"] = f'https://{ip}:6443'
            config["clusters"][0]["name"] = self.node
            config["users"][0]["name"] = self.node
            config["contexts"][0]["name"] = self.node
            config["contexts"][0]["context"]["cluster"] = self.node
            config["contexts"][0]["context"]["user"] = self.node
            config["current-context"] = self.node

        elif self.config["kubernetes"]["role"] == "worker":

            config = requests.get(
                f'http://{self.config["kubernetes"]["cluster"]}-klot-io.local/api/kubectl',
                headers={"x-klot-io-password": self.config["account"]['password']},
            ).json()["kubectl"]

            self.execute(" ".join([
                'INSTALL_K3S_VERSION=v0.9.1',
                f'K3S_URL={config["clusters"][0]["cluster"]["server"]}',
                f'K3S_CLUSTER_SECRET={self.config["account"]["password"]}',
                '/opt/klot-io/bin/k3s.sh',
                'agent'
            ]))

        self.execute("mkdir -p /home/pi/.kube")
        self.execute("rm -f /home/pi/.kube/config")

        with open("/home/pi/.kube/config", "w") as config_file:
            yaml.safe_dump(config, config_file, default_flow_style=False)

        self.execute("sudo chown pi:pi /home/pi/.kube/config")

        if self.config["kubernetes"]["role"] == "master":
            self.execute("sudo -u pi -- kubectl apply -f /opt/klot-io/kubernetes/klot-io-app-crd.yaml")
            self.execute("sudo -u pi -- kubectl apply -f /opt/klot-io/kubernetes/klot-io-apps.yaml")

    def content(self, source):

        if "url" in source:

            url = source["url"]

        elif "site" in source and source["site"] == "github.com":

            if "repo" not in source:
                raise AppException(f"missing source.repo for {source['site']}")

            repo = source["repo"]
            version = source.get("version", "master")

            url = f"https://raw.githubusercontent.com/{repo}/{version}/"

        else:

            raise Exception(f"cannot define {source}")

        if url.endswith("/"):

            path = source.get("path", "klot-io-app.yaml")
            url = f"{url}{path}"

        print(f"requesting {url}")

        response = requests.get(url)

        if response.status_code != 200:
            raise Exception(f"error from source {source} url: {url} - {response.status_code}: {response.text}")

        return response.text

    def discover(self, name, source, action):

        try:
            pykube.KlotIOApp.objects(self.kube).get(name=name).obj
            return
        except pykube.ObjectDoesNotExist:
            pass

        print(f"discovering {name} with {source} for {action}")

        obj = {
            "apiVersion": "klot.io/v1",
            "kind": "KlotIOApp",
            "metadata": {
                "name": name,
            },
            "source": source,
            "action": action,
            "status": "Discovered"
        }

        pykube.KlotIOApp(self.kube, obj).create()

    def define(self, obj):

        print(f"defining {obj['metadata']['name']} from {obj['source']}")

        definition = yaml.safe_load(self.content(obj['source']))

        if not isinstance(definition, dict):
            raise Exception(f"source {obj['source']} produced non dict {definition}")

        if "spec" not in definition:
            raise Exception(f"source {obj['source']} missing spec {definition}")

        if obj['metadata']['name'] != definition.get("metadata",{}).get("name"):
            raise Exception(f"source {obj['source']} name does not match {obj['metadata']['name']} {definition}")

        obj["spec"] = definition['spec']
        obj["status"] = "Defined"

        for app in obj["spec"].get("requires", []) + obj["spec"].get("recommends", []):
            self.discover(app['name'], app['source'], 'Preview')

    def act(self, name, action):

        obj = pykube.KlotIOApp.objects(self.kube).get(name=name).obj

        if obj.get("action", "Preview") == "Install" and action == "Preview":
            return

        print(f"setting {name} for {action}")

        obj["action"] = action

        pykube.KlotIOApp(self.kube, obj).replace()

    def download(self, obj):

        print(f"downloading {obj['metadata']['name']} from {obj['source']}")

        obj["resources"] = []

        for manifest in obj["spec"]["manifests"]:

            source = copy.deepcopy(obj["source"])
            source.update(manifest)

            obj["resources"].extend(list(yaml.safe_load_all(self.content(source))))

        obj["resources"].sort(key= lambda resource: RESOURCES.index(resource["kind"]) if resource["kind"] in RESOURCES else len(RESOURCES))
        obj["status"] = "Downloaded"

        for app in obj["spec"].get("requires", []):

            self.act(app['name'], 'Preview')

            if "integrations" in app:

                obj.setdefault("integrations", [])

                for integration in app["integrations"]:

                    files = {}

                    name = integration.get("name", os.path.basename(integration["path"]))

                    source = copy.deepcopy(obj["source"])
                    source.update(integration)

                    files[name] = self.content(source)

                obj["integrations"].append({
                    "app": app["name"],
                    "files": files
                })

    def display(self, obj):

        display = [obj["kind"]]

        if "namespace" in obj["metadata"] and obj["metadata"]["namespace"]:
            display.append(obj["metadata"]["namespace"])

        display.append(obj["metadata"]["name"])

        return "/".join(display)

    def namespace(self, obj):

        print(f"creating namespace {obj['spec']['namespace']}")

        obj = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": obj['spec']['namespace'],
            }
        }

        try:
            pykube.Namespace(self.kube, obj).replace()
        except pykube.PyKubeError:
            pykube.Namespace(self.kube, obj).delete()
            pykube.Namespace(self.kube, obj).create()

    def configmap(self, obj):

        print(f"creating configmap for {obj['metadata']['name']}")

        obj = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "namespace": obj["spec"]["namespace"],
                "name": "config",
            },
            "data": {}
        }

        try:
            pykube.ConfigMap(self.kube, obj).replace()
        except pykube.PyKubeError:
            pykube.ConfigMap(self.kube, obj).delete()
            pykube.ConfigMap(self.kube, obj).create()

    def create(self, obj):

        self.namespace(obj)
        self.configmap(obj)

        for app in obj["spec"].get("requires", []):
            self.act(app['name'], 'Install')

        if "settings" in obj["spec"] and "settings" not in obj:
            print(f"need settings for {obj['metadata']['name']}")
            obj['status'] = "NeedSettings"
            return

        print(f"checking requirements for {obj['metadata']['name']}")

        for app in obj["spec"].get("requires", []):
            if pykube.KlotIOApp.objects(self.kube).get(name=app['name']).obj.get("status") != "Installed":
                print(f"need {app['name']} for {obj['metadata']['name']}")
                return

        print(f"creating {obj['metadata']['name']}")

        for resource in obj["resources"]:

            if resource["kind"] == "Namespace":
                continue

            print(f"applying {self.display(resource)}")
            Resource = getattr(pykube, resource["kind"])
            try:
                Resource(self.kube, resource).replace()
            except pykube.PyKubeError:
                Resource(self.kube, resource).delete()
                Resource(self.kube, resource).create()

        obj["created"] = True
        obj["status"] = "Installing"

    def url(self, obj):

        url = f"{obj['spec']['url']['protocol']}://{obj['spec']['url']['host'].replace('.', '-')}-{self.node}.local"

        if "port" in url:
            url = f"{url}:{obj['spec']['url']['port']}"

        if "path" in url:
            url = f"{url}/{obj['spec']['url']['path']}"

        return url

    def integration(self, obj, integration):

        print(f"adding integration from {obj['metadata']['name']} to {integration['app']}")

        app = pykube.KlotIOApp.objects(self.kube).get(name=integration["app"]).obj
        config = pykube.ConfigMap.objects(self.kube).filter(namespace=app["spec"]["namespace"]).get(name="config").obj
        config.setdefault("data", {})

        for name, content in integration["files"].items():
            config["data"][f"integration_{obj['metadata']['name']}_{name}"] = content

        pykube.ConfigMap(self.kube, config).replace()

    def check(self, obj):

        print(f"checking {obj['metadata']['name']}")

        url = None

        for resource in obj["resources"]:

            print(f"checking {self.display(resource)} status")

            check = getattr(pykube, resource["kind"])(self.kube, resource)

            try:
                check.reload()
            except pykube.PyKubeError:
                print(f"failed to reload {self.display(resource)}")
                return False

            if resource["kind"] == "Job":

                expected = 1
                actual = check.obj.get("status", {}).get("succeeded", 0)

            elif resource["kind"] == "DaemonSet":

                expected = check.obj.get("status", {}).get("desiredNumberScheduled", 0)
                actual = check.obj.get("status", {}).get("numberReady", 0)

            elif resource["kind"] == "Deployment":

                expected = check.obj.get("status", {}).get("replicas", 0)
                actual = check.obj.get("status", {}).get("readyReplicas", 0)

            else:

                continue

            if expected != actual:
                print(f"{self.display(resource)} not ready {expected} != {actual}")
                return False

        if "url" in obj["spec"]:

            url = self.url(obj)
            print(f"checking {url}")

            try:

                requests.get(url).raise_for_status()

            except Exception as exception:

                print(f"{url} not ready {exception}")
                return False

            obj['url'] = url

        for integration in obj.get("integrations", []):

            self.integration(obj, integration)

        print(f"{obj['metadata']['name']} installed")

        obj["status"] = "Installed"

        return True

    def destroy(self, obj):

        print(f"destroying {self.display(obj)}")

        for resource in reversed(obj["resources"]):

            if resource["kind"] == "Namespace":
                continue

            print(f"deleting {self.display(resource)}")
            try:
                getattr(pykube, resource["kind"])(self.kube, resource).delete()
            except pykube.PyKubeError as exception:
                print(f"failed to delete {self.display(resource)}: {exception}")

        try:
            pykube.ConfigMap.objects(self.kube).filter(namespace=obj["spec"]["namespace"]).get(name="config").delete()
        except pykube.PyKubeError as exception:
            print(f"failed to delete ConfigMap/{obj['spec']['namespace']}/config: {exception}")

        try:
            pykube.Namespace.objects(self.kube).get(name=obj["spec"]["namespace"]).delete()
        except pykube.PyKubeError as exception:
            print(f"failed to delete Namespace/{obj['spec']['namespace']}: {exception}")

        if "created" in obj:
            del obj["created"]

        if "url" in obj:
            del obj["url"]

        obj["action"] = "Preview"
        obj["status"] = "Downloaded"

    def apps(self):

        for obj in [app.obj for app in pykube.KlotIOApp.objects(self.kube).filter()]:

            obj.setdefault("status", "Discovered")
            obj.setdefault("action", "Preview")

            if obj["action"] == "Retry" or obj["status"] == "NeedSettings":
                continue

            try:

                if "spec" not in obj:
                    self.define(obj)
                elif "resources" not in obj:
                    self.download(obj)
                elif obj['action'] == "Install" and "created" not in obj:
                    self.create(obj)
                elif obj['action'] == "Install" and obj.get("status") in ["Installing"]:
                    if not self.check(obj):
                        continue
                elif obj['action'] == "Uninstall":
                    self.destroy(obj)
                else:
                    continue

            except Exception as exception:

                obj["action"] = "Retry"
                obj["status"] = "Error"
                obj["error"] = traceback.format_exc().splitlines()
                traceback.print_exc()

            pykube.KlotIOApp(self.kube, obj).replace()

    def nginx(self, expected):

        actual = {}

        for nginx_path in glob.glob("/etc/nginx/conf.d/*.conf"):

            host = nginx_path.split("/")[-1].split(".conf")[0]
            external = None
            actual[host] = {"servers": []}

            with open(nginx_path, "r") as nginx_file:
                for nginx_line in nginx_file:
                    if "listen" in nginx_line:
                        external = int(nginx_line.split()[-1][:-1])
                    if "proxy_pass" in nginx_line:
                        actual[host]["servers"].append({
                            "protocol": nginx_line.split(":")[0].split(" ")[-1],
                            "external": external,
                            "internal": int(nginx_line.split(":")[-1].split("/")[0])
                        })
                        actual[host]["ip"] = nginx_line.split("/")[2].split(":")[0]

        if expected != actual:

            self.differs(expected, actual)
            self.execute("rm -f /etc/nginx/conf.d/*.conf")

            for host in expected:
                with open(f"/etc/nginx/conf.d/{host}.conf", "w") as nginx_file:
                    for server in expected[host]["servers"]:
                        nginx_file.write(SERVER % (server["external"], host, server["protocol"], expected[host]["ip"], server["internal"]))

            self.execute("systemctl reload nginx")

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
                        "external": port["port"],
                        "internal": port["targetPort"]
                    })
                elif port["name"].lower().startswith("http"):
                    servers.append({
                        "protocol": "http",
                        "external": port["port"],
                        "internal": port["targetPort"]
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

            host = ("%s-%s-%s-klot-io.local" % (
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

        for tmp_file in list(glob.glob("/tmp/tmp??????")):
            if past > os.path.getmtime(tmp_file):
                os.remove(tmp_file)

    def process(self):

        if os.path.exists("/boot/klot-io/reset"):
            self.reset()

        if os.path.exists("/boot/klot-io/lib/config.py"):
            self.restart()

        self.reload()
        self.load()
        self.uninitialized()

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
