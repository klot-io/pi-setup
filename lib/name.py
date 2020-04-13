import os
import time
import yaml
import socket
import pykube
import dnslib
import dnslib.server

class KlotIOResolver():

    def __init__(self, daemon):

        self.daemon = daemon

    def a_rr(self, host, ip):

        return dnslib.RR.fromZone(f"{host}. 15 A {ip}.")

    def cname_rr(self, host, alias):

        return dnslib.RR.fromZone(f"{host}. 15 CNAME {alias}.")

    def resolve(self, request, handler):

        reply = request.reply()

        fqdn = '.'.join([piece.decode('utf-8') for piece in request.questions[0].qname.label])

        if fqdn in self.daemon.ips:
            reply.add_answer(*self.a_rr(fqdn, self.daemon.ips[fqdn]))
        elif fqdn in self.daemon.aliases:
            reply.add_answer(*self.cname_rr(fqdn, self.daemon.aliases[fqdn]))
            reply.add_answer(*self.a_rr(self.daemon.aliases[fqdn], self.daemon.ips[self.daemon.aliases[fqdn]]))
        else:
            try:
                reply = dnslib.DNSRecord.parse(request.send(self.daemon.upstream, 53, tcp=(handler.protocol != 'udp'), timeout=5))
            except socket.timeout:
                reply.header.rcode = getattr(dnslib.RCODE, 'NXDOMAIN')

        return reply

class Daemon(object):

    def __init__(self):

        self.clear()

    def recurse(self):

        with open("/etc/resolv.conf", "r") as resolv_file:
            for resolv_line in resolv_file:
                if "nameserver" in resolv_line:
                    self.upstream = resolv_line.split(' ')[-1].strip()

    def clear(self):

        self.ips = {}
        self.aliases = {}
        self.cluster = None
        self.kube = None
        self.recurse()

    def config(self):

        if (
            not os.path.exists("/opt/klot-io/config/kubernetes.yaml") or
            not os.path.exists("/home/pi/.kube/config")
        ):
            self.clear()
            return False

        if not self.cluster or not self.kube:

            with open("/opt/klot-io/config/kubernetes.yaml", "r") as yaml_file:
                self.cluster = yaml.safe_load(yaml_file)["cluster"]

            self.kube = pykube.HTTPClient(pykube.KubeConfig.from_file("/home/pi/.kube/config"))

        return True

    def nodes(self):

        ips = {}

        for node in [node.obj for node in pykube.Node.objects(self.kube).filter()]:

            ip = None
            host = None

            for address in node["status"]["addresses"]:
                if address["type"] == "InternalIP":
                    ip = address["address"]
                elif address["type"] == "Hostname":
                    host = f"{address['address']}.local"

            ips[host] = ip

        return ips

    def services(self):

        aliases = {}

        for service in [service.obj for service in pykube.Service.objects(self.kube).filter(namespace=pykube.all)]:

            if (
                "type" not in service["spec"] or service["spec"]["type"] != "LoadBalancer" or
                "ports" not in service["spec"] or "selector" not in service["spec"] or
                "namespace" not in service["metadata"]
            ):
                continue

            name = service["metadata"]["name"]
            namespace = service["metadata"]["namespace"]

            servers = False

            for port in service["spec"]["ports"]:

                if "name" not in port:
                    continue

                if port["name"].lower().startswith("http"):
                    servers = True

            if not servers:
                continue

            nodes = []

            for pod in [pod.obj for pod in pykube.Pod.objects(self.kube).filter(
                namespace=service["metadata"]["namespace"],
                selector=service["spec"]["selector"]
            )]:
                if "nodeName" in pod["spec"] and "podIP" in pod["status"]:
                    nodes.append(pod["spec"]["nodeName"])

            if not nodes:
                continue

            node = f"{sorted(nodes)[0]}.local"
            host = f"{name}.{namespace}.{self.cluster}-klot-io.local"

            aliases[host] = node

        return aliases

    def process(self):

        if self.config():
            self.ips = self.nodes()
            self.aliases = self.services()

    def run(self):

        resolver = KlotIOResolver(self)
        logger = dnslib.server.DNSLogger(prefix=False)
        server = dnslib.server.DNSServer(resolver,port=53,address="0.0.0.0",logger=logger)
        server.start_thread()

        while True:
            self.process()
            time.sleep(10)