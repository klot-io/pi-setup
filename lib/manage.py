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
            return {"error": f"invalid service: {sevice}"}, 400

        reader = systemd.journal.Reader()
        reader.add_match(_SYSTEMD_UNIT="nginx.service" if service == "gui" else f"klot-io-{service}.service")
        reader.seek_tail()

        back = int(flask.request.args["back"]) if "back" in flask.request.args else 60

        lines = []

        for index in range(back):

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
            if os.path.exists(f"/opt/klot-io/config/{section}.yaml"):
                with open(f"/opt/klot-io/config/{section}.yaml", "r") as config_file:
                    originals[section] = yaml.safe_load(config_file)
            else:
                originals[section] = {}

        return originals

    @require_auth
    def options(self):

        if self.name not in flask.request.json:
            return {"error": f"missing {self.name}"}

        fields = self.fields(flask.request.json[self.name])

        if not fields.validate():
            return {"fields": fields.to_list(), "errors": fields.errors}
        else:
            return {"fields": fields.to_list()}

    @require_auth
    def post(self):

        if self.name not in flask.request.json:
            return {"error": f"missing {self.name}"}, 400

        fields = self.fields(flask.request.json[self.name])

        if not fields.validate():
            return {"fields": fields.to_list(), "errors": fields.errors}, 400

        for section in self.sections:
            with open(f"/opt/klot-io/config/{section}.yaml", "w") as config_file:
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
            return {"error": f"missing {self.name}"}

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

        if not os.path.exists("/var/lib/rancher/k3s"):

            status = "Uninitialized"

        elif os.path.exists("/etc/systemd/system/k3s-agent.service"):

            status = "Joined"

        elif not os.path.exists("/home/pi/.kube/config"):

            status = "Initializing"

        else:

            status = "NotReady"

            for node in pykube.Node.objects(kube()).filter():
                for condition in node.obj["status"]["conditions"]:
                    if condition["type"] == "Ready" and condition["status"]:
                        if node.obj["metadata"]["name"] != platform.node():
                            status = "Workers"
                        elif status == "NotReady":
                            status = "Master"

            if status == "Workers":
                for obj in [app.obj for app in pykube.App.objects(kube()).filter()]:
                    if obj.get("status") == "Installed" and "url" in obj:
                        status = "Apps"
                        break

        load = [float(value) for value in subprocess.check_output("uptime").decode('utf-8').split("age: ")[-1].split(', ')]
        memory = subprocess.check_output("free").decode('utf-8').split("\n")[:-1]
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
                        f"http://{node['name']}.local/api/status", timeout=5,
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
            return {"error": f"missing {self.name}"}, 400

        if "name" not in flask.request.json[self.name]:
            return {"error": f"missing {self.name}.name"}, 400

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
            return {"error": f"missing {self.name}"}, 400

        node = flask.request.json[self.name]

        try:

            pykube.Node.objects(kube()).get(name=node).delete()

            os.system(f"sudo sed -i '/{node}/d' /var/lib/rancher/k3s/server/cred/node-passwd")

            config = Config.load()

            config["kubernetes"] = {"role": "reset"}

            response = requests.post(
                f"http://{node}.local/api/config",
                headers={"x-klot-io-password": config["account"]["password"]},
                json={"config": config}
            )

            return response.json(), response.status_code

        except pykube.ObjectDoesNotExist:

            return {"error": f"node {flask.request.json[self.name]} not found"}, 404


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
            "version": obj["spec"].get("version", ''),
            "namespace": obj["spec"]["namespace"],
            "description": obj["spec"].get("description", ''),
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

        if "name" not in flask.request.json:
            return {"error": "missing name"}, 400

        if "source" not in flask.request.json:
            return {"error": "missing source"}, 400

        name = flask.request.json["name"]
        source = flask.request.json["source"]

        if "url" in source:

            url = source["url"]

        elif "site" in source and source["site"] == "github.com":

            if "repo" not in source:
                return {"error": f"missing source.repo for {source['site']}"}, 400

            repo = source["repo"]
            version = source["version"] if "version" in source else "master"

            url = f"https://raw.githubusercontent.com/{repo}/{version}/"

        else:

            return {"error": f"need url or github {source}"}, 400

        if url.endswith("/"):

            path = source["path"] if "path" in source else "klot-io-app.yaml"
            url = f"{url}/{path}"

        response = requests.get(url)

        if response.status_code != 200:
            return {f"error from {url}": response.text}, response.status_code

        obj = yaml.safe_load(response.text)

        if not isinstance(obj, dict):
            return {"error": f"{source} produced non dict {obj}"}, 400

        if obj["apiVersion"] != "klot.io/v1":
            return {"error": f"{source} apiVersion not klot.io/v1 {obj}"}, 400

        if obj["kind"] != "App":
            return {"error": f"{source} kind not App {obj}"}, 400

        if "spec" not in obj:
            return {"error": f"{source} missing spec {obj}"}, 400

        if "metadata" not in obj:
            return {"error": f"{source} missing metadata {obj}"}, 400

        if "version" not in obj["metadata"]:
            return {"error": f"{source} missing metadata.version {obj}"}, 400

        if name != obj["metadata"].get("name"):
            return {"error": f"{source} name does not match {name} {obj}"}, 400

        obj["source"] = source

        if "action" in flask.request.json:
            obj["action"] = flask.request.json["action"]

        pykube.App(kube(), obj).create()

        return {"message": f"{obj['metadata']['name']} queued for preview"}, 202

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
            return {"error": f"Can't delete Installed {name}. Uninstall first."}

        pykube.App(kube(), obj).delete()

        return {"message": f"{name} deleted"}, 201


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
                            node_label == f"{app_label['app']}/{app_label['name']}" and
                            obj["metadata"]["labels"][node_label] == app_label["value"]
                        ):
                            app_label["nodes"].append(obj["metadata"]["name"])

        return {self.plural: sorted(labels, key=lambda label: f"{label['app']}/{label['name']}={label['value']}")}

    @require_auth
    @require_kube
    def post(self):

        if self.singular not in flask.request.json:
            return {"error": f"missing {self.singular}"}, 400

        label = flask.request.json[self.singular]

        errors = []

        for field in ["app", "name", "value", "node"]:
            if field not in label:
                errors.append(f"missing {self.singular}.{field}")

        if errors:
            return {"errors": errors}, 400

        app_labels = {}

        for obj in [app.obj for app in pykube.App.objects(kube()).filter()]:
            if "labels" in obj["spec"]:
                for app_label in obj["spec"]["labels"]:
                    app_labels[f"{obj['metadata']['name']}/{app_label['name']}={app_label['value']}"] = app_label

        if f"{label['app']}/{label['name']}={label['value']}" not in app_labels:
            return {"error": f"invalid label {label['app']}/{label['name']}={label['value']}"}, 400

        app_label = app_labels[f"{label['app']}/{label['name']}={label['value']}"]

        obj = pykube.Node.objects(kube()).filter().get(name=flask.request.json[self.singular]["node"]).obj

        if obj["metadata"]["name"] == platform.node() and ("master" not in app_label or not app_label["master"]):
            return {"error": f"can't label master with {label['app']}/{label['name']}={label['value']}"}, 400

        if "labels" not in obj["metadata"]:
            obj["metadata"]["labels"] = {}

        obj["metadata"]["labels"][f"{label['app']}/{label['name']}"] = label["value"]

        pykube.Node(kube(), obj).replace()

        return {"message": f"{label['node']} labeled {label['app']}/{label['name']}={label['value']}"}

    @require_auth
    @require_kube
    def delete(self):

        if self.singular not in flask.request.json:
            return {"error": f"missing {self.singular}"}, 400

        label = flask.request.json[self.singular]

        errors = []

        for field in ["app", "name", "node"]:
            if field not in label:
                errors.append(f"missing {self.singular,}.{field}")

        if errors:
            return {"errors": errors}, 400

        app_labels = []

        for obj in [app.obj for app in pykube.App.objects(kube()).filter()]:
            if "labels" in obj["spec"]:
                for app_label in obj["spec"]["labels"]:
                    app_labels.append(f"{obj['metadata']['name']}/{app_label['name']}")

        if f"{label['app']}/{label['name']}" not in app_labels:
            return {"error": f"invalid label {label['app']}/{label['name']}"}, 400

        obj = pykube.Node.objects(kube()).filter().get(name=flask.request.json[self.singular]["node"]).obj

        if "labels" in obj["metadata"] and f"{label['app']}/{label['name']}" in obj["metadata"]["labels"]:
            del obj["metadata"]["labels"][f"{label['app']}/{label['name']}"]

        pykube.Node(kube(), obj).replace()

        return {"message": f"{label['node']} unlabeled {label['app']}/{label['name']}"}
