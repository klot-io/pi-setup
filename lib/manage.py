import os
import yaml
import requests
import platform
import calendar
import functools
import subprocess

import flask
import flask_restful
import opengui
import pykube

def app():

    app = flask.Flask("klot-io-api")

    app.kube = None

    api = flask_restful.Api(app)

    api.add_resource(Health, '/health')
    api.add_resource(Log, '/log/<string:service>')
    api.add_resource(Config, '/config')
    api.add_resource(Status, '/status')
    api.add_resource(Kubectl, '/kubectl')
    api.add_resource(Node, '/node')
    api.add_resource(Namespace, '/namespace')
    api.add_resource(Event, '/event')
    api.add_resource(Pod, '/pod')
    api.add_resource(PodRD, '/pod/<string:pod>')
    api.add_resource(AppLP, '/app')
    api.add_resource(AppRIU, '/app/<string:name>')
    api.add_resource(Label, '/label')

    return app


def kube():

    if not os.path.exists("/home/pi/.kube/config"):

        flask.current_app.kube = None

    elif not flask.current_app.kube:

        flask.current_app.kube = pykube.HTTPClient(pykube.KubeConfig.from_file("/home/pi/.kube/config"))

    return flask.current_app.kube


def require_auth(endpoint):
    @functools.wraps(endpoint)
    def wrap(*args, **kwargs):

        with open("/opt/klot-io/config/account.yaml", "r") as config_file:
            password = yaml.safe_load(config_file)["password"]

        if "x-klot-io-password" not in flask.request.headers:
            return {"error": "missing password"}, 400

        if flask.request.headers["x-klot-io-password"] != password:
            return {"error": "invalid password"}, 401

        return endpoint(*args, **kwargs)

    return wrap


def require_kube(endpoint):
    @functools.wraps(endpoint)
    def wrap(*args, **kwargs):

        if not kube():
            return {"error": "kubernetes not available"}, 503

        return endpoint(*args, **kwargs)

    return wrap


class Health(flask_restful.Resource):
    def get(self):
        return {"message": "OK"}


class Log(flask_restful.Resource):

    @require_auth
    def get(self, service):

        import systemd.journal

        if service not in ["dns", "daemon", "api", "gui"]:
            return {"error": "invalid service: %s" % sevice}, 400

        reader = systemd.journal.Reader()
        reader.add_match(_SYSTEMD_UNIT="nginx.service" if service == "gui" else "klot-io-%s.service" % service)
        reader.seek_tail()

        back = int(flask.request.args["back"]) if "back" in flask.request.args else 60

        lines = []

        for index in xrange(back):

            line = reader.get_previous()

            if not line:
                break
            
            lines.insert(0, {
                "timestamp": calendar.timegm(line["__REALTIME_TIMESTAMP"].timetuple()),
                "message": line['MESSAGE']
            }) 

        return {"lines": lines}


class Config(flask_restful.Resource):

    name = "config"
    sections = ["account", "network", "kubernetes"]

    @classmethod
    def fields(cls, values):

        fields = opengui.Fields(values, cls.load(), [
            {
                "name": "account",
                "fields": [
                    {
                        "name": "password"
                    },
                    {
                        "name": "ssh",
                        "options": [
                            "disabled",
                            "enabled"
                        ],
                        "default": "disabled"
                    }
                ]
            },
            {
                "name": "network",
                "fields": [
                    {
                        "name": "interface",
                        "options": [
                            "eth0",
                            "wlan0"
                        ],
                        "labels": {
                            "eth0": "wired",
                            "wlan0": "wireless"
                        },
                        "trigger": True
                    }
                ]
            },
            {
                "name": "kubernetes",
                "fields": [
                    {
                        "name": "role",
                        "options": [
                            "master",
                            "worker",
                            "reset"
                        ],
                        "trigger": True
                    }
                ]
            }
        ])

        if fields["kubernetes"]["role"].original is not None and fields["kubernetes"]["role"].original != "reset":
            fields["kubernetes"]["role"].options = [fields["kubernetes"]["role"].original, "reset"]

        if fields["network"]["interface"].value == "wlan0":
            fields["network"].extend([
                {
                    "name": "country",
                    "default": "US"
                },
                {
                    "name": "ssid"
                },
                {
                    "name": "psk",
                    "label": "password",
                    "optional": True
                }
            ])

        if fields["kubernetes"]["role"].value and fields["kubernetes"]["role"].value != "reset":
            fields["kubernetes"].append({
                "name": "cluster"
            })

        if fields["kubernetes"]["role"].value == "worker":
            fields["kubernetes"].append({
                "name": "name"
            })

        return fields

    @classmethod
    def load(cls):

        originals = {}

        for section in cls.sections:
            if os.path.exists("/opt/klot-io/config/%s.yaml" % section):
                with open("/opt/klot-io/config/%s.yaml" % section, "r") as config_file:
                    originals[section] = yaml.safe_load(config_file)
            else:
                originals[section] = {}

        return originals

    @require_auth
    def options(self):

        if self.name not in flask.request.json:
            return {"error": "missing %s" % self.name}

        fields = self.fields(flask.request.json[self.name])

        if not fields.validate():
            return {"fields": fields.to_list(), "errors": fields.errors}
        else:
            return {"fields": fields.to_list()}

    @require_auth
    def post(self):

        if self.name not in flask.request.json:
            return {"error": "missing %s" % self.name}, 400

        fields = self.fields(flask.request.json[self.name])

        if not fields.validate():
            return {"fields": fields.to_list(), "errors": fields.errors}, 400

        for section in self.sections:
            with open("/opt/klot-io/config/%s.yaml" % section, "w") as config_file:
                yaml.safe_dump(fields[section].values, config_file, default_flow_style=False)

        return {self.name: flask.request.json[self.name]}, 202

    @require_auth
    def get(self):

        return {self.name: self.load()}


class Kubectl(flask_restful.Resource):

    name = "kubectl"

    @staticmethod
    def load():

        loaded = {}

        if os.path.exists("/home/pi/.kube/config"):
            with open("/home/pi/.kube/config", "r") as config_file:
                loaded = yaml.safe_load(config_file)

        return loaded

    @require_auth
    def get(self):

        local = self.load()

        if not local:
            return {"error": "kubectl config not found"}, 404

        return {self.name: local}

    @require_auth
    def post(self):

        local = self.load()

        if not local:
            return {"error": "kubectl config not found"}, 404

        if self.name not in flask.request.json:
            return {"error": "missing %s" % self.name}

        remote = flask.request.json[self.name]

        for key in ["clusters", "users", "contexts"]:
            remove = None
            for index, item in enumerate(remote[key]):
                if item["name"] == local["current-context"]:
                    remove = index
            if remove is not None:
                 remote[key].pop(remove)

            remote[key].extend(local[key])

        remote["current-context"] = local["current-context"]

        return {self.name: remote}


class Status(flask_restful.Resource):

    @require_auth
    def get(self):

        if not os.path.exists("/opt/klot-io/config/kubernetes.yaml"):

            status = "Uninitialized"

        elif os.path.exists("/etc/kubernetes/bootstrap-kubelet.conf"):

            status = "Joined"

        elif not os.path.exists("/etc/kubernetes/admin.conf"):

            status = "Initializing"

        elif not os.path.exists("/home/pi/.kube/config"):

            status = "Creating"

        else:

            status = "NotReady"

            for node in pykube.Node.objects(kube()).filter():
                for condition in node.obj["status"]["conditions"]:
                    if condition["type"] == "Ready" and condition["status"]:
                        if node.obj["metadata"]["name"] != platform.node():
                            status = "Workers"
                        elif status == "NotReady":
                            status = "Master"

        load = [float(value) for value in subprocess.check_output("uptime").split("age: ")[-1].split(', ')]
        memory = subprocess.check_output("free").split("\n")[:-1]
        titles = memory[0].split()
        values = memory[1].split()[1:]
        free = {title: int(values[index]) for index, title in enumerate(titles)}

        return {"status": status, "load": load, "free": free}


class Node(flask_restful.Resource):

    name = "node"

    @staticmethod
    def uninitialized():
        return os.path.exists("/opt/klot-io/config/uninitialized")

    @require_auth
    def get(self):

        nodes = []
        master = None
        workers = []

        if kube():

            for obj in [node.obj for node in pykube.Node.objects(kube()).filter()]:

                node = {
                    "name": obj["metadata"]["name"],
                    "status": "NotReady"
                }

                try:

                    response = requests.get(
                        "http://%s.local/api/status" % node["name"], timeout=5,
                        headers={"x-klot-io-password": flask.request.headers["x-klot-io-password"]}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        node["load"] = data["load"]
                        node["free"] = data["free"]

                except:

                    pass

                if "labels" in obj["metadata"]:
                    node["labels"] = obj["metadata"]["labels"]

                for condition in obj["status"]["conditions"]:
                    if condition["type"] == "Ready" and condition["status"] == "True":
                        node["status"] = "Ready"

                if node["name"] == platform.node():
                    node["role"] = "master"
                    master = node
                else:
                    node["role"] = "worker"
                    workers.append(node)

            nodes.append(master)

        if self.uninitialized():

            try:

                response = requests.get(
                    "http://klot-io.local/api/status", timeout=5,
                    headers={"x-klot-io-password": 'kloudofthings'}
                )

                if response.status_code != 200:

                    response = requests.get(
                        "http://klot-io.local/api/status", timeout=5,
                        headers={"x-klot-io-password": flask.request.headers["x-klot-io-password"]}
                    )

                if response.status_code == 200:

                    data = response.json()

                    nodes.append({
                        "name": "klot-io",
                        "status": data["status"],
                        "role": None,
                        "load": data["load"],
                        "free": data["free"]
                    })

            except:

                pass

        nodes.extend(sorted(workers, key=lambda node: node["name"]))

        return {"nodes": nodes}

    @require_auth
    def post(self):

        if not self.uninitialized():
            return {"error": "uninitialized node not found"}, 404

        if self.name not in flask.request.json:
            return {"error": "missing %s" % self.name}, 400

        if "name" not in flask.request.json[self.name]:
            return {"error": "missing %s.name" % self.name}, 400

        config = Config.load()

        config["kubernetes"]["role"] = "worker"
        config["kubernetes"]["name"] = flask.request.json[self.name]["name"]

        response = requests.post(
            "http://klot-io.local/api/config",
            headers={"x-klot-io-password": "kloudofthings"},
            json={"config": config}
        )

        if response.status_code != 202:

            response = requests.post(
                "http://klot-io.local/api/config",
                headers={"x-klot-io-password": flask.request.headers["x-klot-io-password"]},
                json={"config": config}
            )

        return response.json(), response.status_code

    @require_auth
    @require_kube
    def delete(self):

        if self.name not in flask.request.json:
            return {"error": "missing %s" % self.name}, 400

        try:

            config = Config.load()

            config["kubernetes"] = {"role": "reset"}

            response = requests.post(
                "http://%s.local/api/config" % flask.request.json[self.name],
                headers={"x-klot-io-password": config["account"]["password"]},
                json={"config": config}
            )

            return response.json(), response.status_code

        except pykube.ObjectDoesNotExist:

            return {"error": "node not found"}, 404


class Namespace(flask_restful.Resource):

    @require_auth
    @require_kube
    def get(self):

        namespaces = []

        for obj in [namespace.obj for namespace in pykube.Namespace.objects(kube()).filter()]:

            namespaces.append(obj["metadata"]["name"])

        return {"namespaces": sorted(namespaces)}


class Event(flask_restful.Resource):

    @require_auth
    @require_kube
    def get(self):

        events = []

        namespace = flask.request.args["namespace"] if "namespace" in flask.request.args else pykube.all

        for obj in [event.obj for event in pykube.Event.objects(kube()).filter(namespace=namespace)]:

            event = {
                "kind": obj["involvedObject"]["kind"],
                "name": obj["involvedObject"]["name"],
                "reason": obj["reason"],
                "message": obj["message"],
                "timestamp": obj["lastTimestamp"]
            }

            if "namespace" in obj["involvedObject"]:
                event["namespace"] = obj["involvedObject"]["namespace"]

            events.append(event)

        return {"events": sorted(events, key=lambda event: event["timestamp"])}


class Pod(flask_restful.Resource):

    @require_auth
    @require_kube
    def get(self):

        pods = []

        namespace = flask.request.args["namespace"] if "namespace" in flask.request.args else pykube.all

        for obj in [pod.obj for pod in pykube.Pod.objects(kube()).filter(namespace=namespace)]:

            pod = {
                "namespace": obj["metadata"]["namespace"],
                "name": obj["metadata"]["name"],
                "status": obj["status"]["phase"],
                "node": None,
                "containers": [container["name"] for container in obj["spec"]["containers"]]
            }

            if "nodeName" in obj["spec"]:
                pod["node"] = obj["spec"]["nodeName"]

            pods.append(pod)

        return {"pods": sorted(pods, key=lambda pod: (pod["namespace"], pod["name"]))}


class PodRD(flask_restful.Resource):

    @require_auth
    @require_kube
    def get(self, pod):

        (namespace, name) = pod.split('.')

        pod = pykube.Pod.objects(kube()).filter(namespace=namespace).get(name=name)

        containers = [container["name"] for container in pod.obj["spec"]["containers"]]

        params = {
            "timestamps": True,
            "tail_lines": 100
        }

        if "tail_lines" in flask.request.args:
            params["tail_lines"] = flask.request.args["tail_lines"]

        log = {}

        for container in containers:
            params["container"] = container
            log[container] = pykube.Pod.objects(kube()).filter(namespace=namespace).get(name=name).logs(**params)

        return {"log": log}

    @require_auth
    @require_kube
    def delete(self, pod):

        (namespace, name) = pod.split('.')

        pod = pykube.Pod.objects(kube()).filter(namespace=namespace).get(name=name).delete()

        return {"deleted": True}, 202


class App(flask_restful.Resource):

    singular = "app"
    plural = "apps"

    @staticmethod
    def to_dict(obj, short=False):

        app = {
            "name": obj["metadata"]["name"],
            "namespace": obj["spec"]["namespace"],
            "description": obj["metadata"]["description"],
            "action": "Download",
            "status": "Discovered"
        }

        if "status" in obj:
            app["status"] = obj["status"]

        if "action" in obj:
            app["action"] = obj["action"]

        if "labels" in obj["spec"]:
            app["labels"] = obj["spec"]["labels"]

        if "url" in obj:
            app["url"] = obj["url"]

        if not short:

            if "error" in obj:
                app["error"] = obj["error"]

            if "source" in obj["spec"]:
                app["source"] = obj["spec"]["source"]

            if "resources" in obj:
                app["resources"] = obj["resources"]

        return app

class AppLP(App):

    @require_auth
    @require_kube
    def get(self):

        apps = []

        for obj in [app.obj for app in pykube.App.objects(kube()).filter()]:

            apps.append(self.to_dict(obj, short=True))

        return {self.plural: sorted(apps, key=lambda app: app["name"])}

    @require_auth
    @require_kube
    def post(self):

        if "source" not in flask.request.json:
            return {"error": "missing source"}, 400

        source = flask.request.json["source"]

        if "url" in source:

            url = source["url"]

        elif "site" in source and source["site"] == "github.com":

            if "repo" not in source:
                return {"error": "missing source.repo for %s" % source["site"]}, 400

            repo = source["repo"]
            version = source["version"] if "version" in source else "master"
            path = source["path"] if "path" in source else "klot-io-app.yaml"

            url = "https://raw.githubusercontent.com/%s/%s/%s" % (repo, version, path)

        else:

            return {"error": "cannot preview %s" % source}, 400

        response = requests.get(url)

        if response.status_code != 200:
            return {"error from %s" % url: response.text}, response.status_code

        obj = yaml.safe_load(response.text)

        if (
            not isinstance(obj, dict) or obj["apiVersion"] != "klot.io/v1" or obj["kind"] != "App" or 
            "spec" not in obj or "source" not in obj['spec'] or obj['spec']["source"] != source or
            "metadata" not in obj or "spec" not in obj or len(obj.keys()) != 4
        ):
            return {"error": "%s produced malformed App %s" % (source, obj)}, 400

        if "action" in flask.request.json:
            obj["action"] = flask.request.json["action"]

        pykube.App(kube(), obj).create()

        return {"message": "%s queued for preview" % obj["metadata"]["name"]}, 202

class AppRIU(App):

    @require_auth
    @require_kube
    def get(self, name):

        obj = pykube.App.objects(kube()).filter().get(name=name).obj

        return {self.singular: self.to_dict(obj)}

    @require_auth
    @require_kube
    def patch(self, name):

        if "action" not in flask.request.json:
            return {"error": "missing action"}, 400

        obj = pykube.App.objects(kube()).filter().get(name=name).obj

        obj["action"] = flask.request.json["action"]

        pykube.App(kube(), obj).replace()

        return {self.singular: self.to_dict(obj)}


    @require_auth
    @require_kube
    def delete(self, name):

        obj = pykube.App.objects(kube()).filter().get(name=name).obj

        if "status" in obj and obj["status"] == "Installed":
            return {"error": "Can't delete Installed %s. Uninstall first." % name}

        pykube.App(kube(), obj).delete()

        return {"message": "%s deleted" % name}, 201


class Label(flask_restful.Resource):

    singular = "label"
    plural = "labels"

    @require_auth
    @require_kube
    def get(self):

        labels = []

        app_filter = {}

        if "app" in flask.request.args:
            app_filter["field_selector"] = {"metadata.name": flask.request.args["app"]}

        node_filter = {}

        if "node" in flask.request.args:
            node_filter["field_selector"] = {"metadata.name": flask.request.args["node"]}

        for obj in [app.obj for app in pykube.App.objects(kube()).filter(**app_filter)]:
            if "labels" in obj["spec"]:
                for label in obj["spec"]["labels"]:
                    labels.append({
                        "app": obj["metadata"]["name"],
                        "name": label["name"],
                        "value": label["value"],
                        "description": label["description"],
                        "master": label["master"] if "master" in label else False,
                        "nodes": []
                    })

        for obj in [node.obj for node in pykube.Node.objects(kube()).filter(**node_filter)]:
            if "labels" in obj["metadata"]:
                for node_label in obj["metadata"]["labels"]:
                    for app_label in labels:
                        if (
                            node_label == "%s/%s" % (app_label["app"], app_label["name"]) and
                            obj["metadata"]["labels"][node_label] == app_label["value"]
                        ):
                            app_label["nodes"].append(obj["metadata"]["name"])

        return {self.plural: sorted(labels, key=lambda label: "%s/%s=%s" % (label["app"], label["name"], label["value"]))}

    @require_auth
    @require_kube
    def post(self):

        if self.singular not in flask.request.json:
            return {"error": "missing %s" % self.singular}, 400

        label = flask.request.json[self.singular]

        errors = []

        for field in ["app", "name", "value", "node"]:
            if field not in label:
                errors.append("missing %s.%s" % (self.singular, field))

        if errors:
            return {"errors": errors}, 400

        app_labels = {}

        for obj in [app.obj for app in pykube.App.objects(kube()).filter()]:
            if "labels" in obj["spec"]:
                for app_label in obj["spec"]["labels"]:
                    app_labels["%s/%s=%s" % (obj["metadata"]["name"], app_label["name"], app_label["value"])] = app_label

        if "%s/%s=%s" % (label["app"], label["name"], label["value"]) not in app_labels:
            return {"error": "invalid label %s/%s=%s" % (label["app"], label["name"], label["value"])}, 400

        app_label = app_labels["%s/%s=%s" % (label["app"], label["name"], label["value"])]

        obj = pykube.Node.objects(kube()).filter().get(name=flask.request.json[self.singular]["node"]).obj

        if obj["metadata"]["name"] == platform.node() and ("master" not in app_label or not app_label["master"]):
            return {"error": "can't label master with %s/%s=%s" % (label["app"], label["name"], label["value"])}, 400

        if "labels" not in obj["metadata"]:
            obj["metadata"]["labels"] = {}

        obj["metadata"]["labels"]["%s/%s" % (label["app"], label["name"])] = label["value"]

        pykube.Node(kube(), obj).replace()
                        
        return {"message": "%s labeled %s/%s=%s" % (label["node"], label["app"], label["name"], label["value"])}

    @require_auth
    @require_kube
    def delete(self):

        if self.singular not in flask.request.json:
            return {"error": "missing %s" % self.singular}, 400

        label = flask.request.json[self.singular]

        errors = []

        for field in ["app", "name", "node"]:
            if field not in label:
                errors.append("missing %s.%s" % (self.singular, field))

        if errors:
            return {"errors": errors}, 400

        app_labels = []

        for obj in [app.obj for app in pykube.App.objects(kube()).filter()]:
            if "labels" in obj["spec"]:
                for app_label in obj["spec"]["labels"]:
                    app_labels.append("%s/%s" % (obj["metadata"]["name"], app_label["name"]))

        if "%s/%s" % (label["app"], label["name"]) not in app_labels:
            return {"error": "invalid label %s/%s" % (label["app"], label["name"])}, 400

        obj = pykube.Node.objects(kube()).filter().get(name=flask.request.json[self.singular]["node"]).obj

        if "labels" in obj["metadata"] and "%s/%s" % (label["app"], label["name"]) in obj["metadata"]["labels"]:
            del obj["metadata"]["labels"]["%s/%s" % (label["app"], label["name"])]

        pykube.Node(kube(), obj).replace()
                        
        return {"message": "%s unlabeled %s/%s" % (label["node"], label["app"], label["name"])}
