import os
import glob
import yaml
import socket
import urlparse
import requests
import platform
import calendar
import functools

import flask
import flask_restful

import pykube

class App(pykube.objects.APIObject):

    version = "klot.io/v1"
    endpoint = "apps"
    kind = "App"

pykube.App = App

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
    api.add_resource(Pod, '/pod')
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
            password = yaml.load(config_file)["password"]

        if "klot-io-password" not in flask.request.headers:
            return {"error": "missing password"}, 400

        if flask.request.headers["klot-io-password"] != password:
            return {"error": "invalid password"}, 401

        return endpoint(*args, **kwargs)

    return wrap


class Health(flask_restful.Resource):
    def get(self):
        return {"message": "OK"}


class Log(flask_restful.Resource):

    @require_auth
    def get(self, service):

        import systemd.journal

        if service not in ["daemon", "api", "gui"]:
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

    @staticmethod
    def settings(values=None):

        if values == None:
            values = {}

        settings = [
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
        ]

        if os.path.exists("/opt/klot-io/config/kubernetes.yaml"):

            with open("/opt/klot-io/config/kubernetes.yaml", "r") as config_file:
                role = yaml.load(config_file)["role"]
            
            if role != "reset":
                settings[2]["fields"][0]["options"] = [role, "reset"]

        if "network" in values and "interface" in values["network"] and \
           values["network"]["interface"] == "wlan0":
            settings[1]["fields"].extend([
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

        if "kubernetes" in values and "role" in values["kubernetes"]: 
        
            if values["kubernetes"]["role"] != "reset":
                settings[2]["fields"].extend([
                    {
                        "name": "cluster"
                    }
                ])

            if values["kubernetes"]["role"] == "worker":
                settings[2]["fields"].extend([
                    {
                        "name": "name"
                    }
                ])

        for setting in settings:
            for field in setting["fields"]:
                if setting["name"] in values and field["name"] in values[setting["name"]]:
                    field["value"] = values[setting["name"]][field["name"]];
                elif "default" in field:
                    field["value"] = field["default"]

        return settings

    @staticmethod
    def validate(settings, values):

        errors = []

        for setting in settings:

            for field in values[setting["name"]]:
                if field not in [field["name"] for field in setting["fields"]]:
                    errors.append("unknown field '%s.%s'" % (setting["name"], field))

            for field in setting["fields"]:

                if (
                    field["name"] not in values[setting["name"]] or 
                    str(values[setting["name"]][field["name"]]) == ""
                ) and (
                    "optional" not in field or not field["optional"]
                ):
                    errors.append("missing field '%s.%s'" % (setting["name"], field["name"]))

                if (
                    "options" in field and field["name"] in values[setting["name"]] and
                    values[setting["name"]][field["name"]] not in field["options"]
                ):
                    errors.append("invalid value '%s' for field '%s.%s'" % (
                        values[setting["name"]][field["name"]], setting["name"], field["name"]
                    ))

            if (
                setting["name"] == "kubernetes" and 
                "role" in values[setting["name"]] and 
                values[setting["name"]]["role"] == "worker" and
                "name" not in values[setting["name"]]
            ):
                errors.append("must specify a kuberentes worker name")

        return errors

    @classmethod
    def load(cls):

        loaded = {}

        for setting in cls.settings():
            if os.path.exists("/opt/klot-io/config/%s.yaml" % setting["name"]):
                with open("/opt/klot-io/config/%s.yaml" % setting["name"], "r") as config_file:
                    loaded[setting["name"]] = yaml.load(config_file)
            else:
                loaded[setting["name"]] = {}

        return loaded

    @require_auth
    def options(self):

        if self.name not in flask.request.json:
            return {"error": "missing %s" % self.name}

        values = flask.request.json[self.name]
        settings = self.settings(values)
        errors = self.validate(settings, values)

        if errors:
            return {"settings": settings, "errors": errors}
        else:
            return {"settings": settings}

    @require_auth
    def post(self):

        if self.name not in flask.request.json:
            return {"error": "missing %s" % self.name}, 400

        values = flask.request.json[self.name]
        settings = self.settings(values)
        errors = self.validate(self.settings(values), values)

        if errors:
            return {"errors": errors}, 400

        for setting in settings:
            with open("/opt/klot-io/config/%s.yaml" % setting["name"], "w") as config_file:
                yaml.safe_dump(values[setting["name"]], config_file, default_flow_style=False)

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
                loaded = yaml.load(config_file)

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

        return {"status": status}


class Node(flask_restful.Resource):

    name = "node"

    def uninitialized(self):

        try:

            socket.gethostbyname('klot-io.local')
            return True

        except:

            return False

    @require_auth
    def get(self):

        nodes = []

        if self.uninitialized():
            nodes.append({
                "name": "klot-io",
                "status": "Uninitialized",
                "role": None
            })

        if kube():

            master = None
            workers = []

            for obj in [node.obj for node in pykube.Node.objects(kube()).filter()]:

                node = {
                    "name": obj["metadata"]["name"],
                    "status": "NotReady"
                }

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

            nodes.extend(sorted(workers, key=lambda node: node["name"]))

        return {"nodes": nodes}

    @require_auth
    def post(self):

        if not self.uninitialized():
            return {"error": "no uninitialized node found"}, 404

        if self.name not in flask.request.json:
            return {"error": "missing %s" % self.name}, 400

        if "name" not in flask.request.json[self.name]:
            return {"error": "missing %s.name" % self.name}, 400

        config = Config.load()

        config["kubernetes"]["role"] = "worker"
        config["kubernetes"]["name"] = flask.request.json[self.name]["name"]

        response = requests.post(
            "http://klot-io.local/api/config",
            headers={"klot-io-password": "kloudofthings"},
            json={"config": config}
        )

        return response.json(), response.status_code

    @require_auth
    def delete(self):

        if not kube():
            return {"error": "not initialized"}, 400

        if self.name not in flask.request.json:
            return {"error": "missing %s" % self.name}, 400

        try:

            pykube.Node.objects(kube()).filter(
                field_selector={"metadata.name": flask.request.json[self.name]}
            ).get().delete()

            config = Config.load()

            config["kubernetes"]["role"] = "reset"

            response = requests.post(
                "http://%s.local/api/config" % flask.request.json[self.name],
                headers={"klot-io-password": config["account"]["password"]},
                json={"config": config}
            )

            return response.json(), response.status_code

        except pykube.ObjectDoesNotExist:

            return {"error": "node not found"}, 404

class Pod(flask_restful.Resource):

    @require_auth
    def get(self):

        pods = []

        if kube():

            namespace = flask.request.args["namespace"] if "namespace" in flask.request.args else pykube.all

            for obj in [pod.obj for pod in pykube.Pod.objects(kube()).filter(namespace=namespace)]:

                pod = {
                    "namespace": obj["metadata"]["namespace"],
                    "name": obj["metadata"]["name"],
                    "status": obj["status"]["phase"],
                    "node": None
                }

                if "nodeName" in obj["spec"]:
                    pod["node"] = obj["spec"]["nodeName"]

                pods.append(pod)

        return {"pods": sorted(pods, key=lambda pod: pod["name"])}


class App(flask_restful.Resource):

    singular = "app"
    plural = "apps"

class AppLP(App):

    @require_auth
    def get(self):

        apps = []

        if kube():

            for obj in [app.obj for app in pykube.App.objects(kube()).filter()]:

                app = {
                    "name": obj["metadata"]["name"],
                    "description": obj["metadata"]["description"],
                    "labels": obj["spec"]["labels"],
                    "status": "Preview"
                }

                if "status" in obj:
                    app["status"] = obj["status"]

                apps.append(app)

        return {self.plural: sorted(apps, key=lambda app: app["name"])}

    @require_auth
    def post(self):

        if not kube():
            return {"error": "kubernetes not available"}, 503

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

        pykube.App(kube(), obj).create()

        return {"message": "%s queued for preview" % obj["metadata"]["name"]}, 202

class AppRIU(App):

    @require_auth
    def get(self, name):

        app = {}

        if kube():

            obj = pykube.App.objects(kube()).filter().get(name=name).obj

            app = {
                "name": obj["metadata"]["name"],
                "description": obj["metadata"]["description"],
                "labels": obj["spec"]["labels"],
                "status": "Preview"
            }

            if "status" in obj:
                app["status"] = obj["status"]

            if "resources" in obj:
                app["resources"] = obj["resources"]

            if "settings" in obj:
                app["settings"] = obj["settings"]

        return {self.singular: app}

    @require_auth
    def post(self, name):

        if not kube():
            return {"error": "kubernetes not available"}, 503

        obj = pykube.App.objects(kube()).filter().get(name=name).obj

        if obj["status"] != "Ready":
            return {"error": "%s App not Ready" % name}

        obj["status"] = "Install"

        pykube.App(kube(), obj).replace()

        return {"message": "%s queued for install" % name}, 201


    @require_auth
    def delete(self, name):

        if not kube():
            return {"error": "kubernetes not available"}, 503

        obj = pykube.App.objects(kube()).filter().get(name=name).obj

        if obj["status"] != "Installed":
            return {"error": "%s App not Installed" % name}

        obj["status"] = "Uninstall"

        pykube.App(kube(), obj).replace()

        return {"message": "%s queued for uninstall" % name}, 201


class Label(flask_restful.Resource):

    singular = "label"
    plural = "labels"

    @require_auth
    def get(self):

        labels = []

        if kube():

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
    def post(self):

        if not kube():
            return {"error": "kubernetes not available"}, 503

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
    def delete(self):

        if not kube():
            return {"error": "kubernetes not available"}, 503

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
