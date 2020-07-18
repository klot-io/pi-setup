import os
import json
import yaml
import requests
import platform
import calendar
import operator
import functools
import subprocess

import flask
import flask_restful
import opengui
import pykube
import google_auth_oauthlib.flow
import google.oauth2.credentials
import googleapiclient.discovery

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
    api.add_resource(AppV, '/app/<string:name>/upgrade')

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
                for obj in [app.obj for app in pykube.KlotIOApp.objects(kube()).filter()]:
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

    def options(self):

        options = []
        master = None
        app = flask.request.args.get("app")
        label = flask.request.args.get("label")
        value = flask.request.args.get("value")
        workers = []

        if kube():

            for obj in [node.obj for node in pykube.Node.objects(kube()).filter()]:

                if app and label and value and obj["metadata"].get("labels", {}).get(f"{app}/{label}") != value:
                    continue

                if obj["metadata"]["name"] == platform.node():
                    master = obj["metadata"]["name"]
                else:
                    workers.append(obj["metadata"]["name"])

            if master is not None:
                options.append(master)

        options.extend(sorted(workers))

        return {"options": options}

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
            "version": obj["source"].get("version", ''),
            "namespace": obj.get("spec", {}).get("namespace", ""),
            "description": obj.get("spec", {}).get("description", ''),
            "action": obj.get("action","Preview"),
            "status": obj.get("status","Discovered"),
            "actions": []
        }

        if "url" in obj:
            app["url"] = obj["url"]

        if "settings" in obj:
            app["settings"] = obj["settings"]

        if "settings" in obj.get("spec", {}) and app["status"] in ["NeedSettings", "Installed"] and app["action"] != "Uninstall":
            app["actions"].append("Settings")

        if app["action"] == "Retry" and "resources" not in obj:
            app["actions"].append("Preview")

        if "created" not in obj:
            actions = ["Delete", "Install", "Upgrade"]
        elif app["action"] != "Uninstall":
            actions = ["Upgrade", "Uninstall"]
        else:
            actions = []

        if app["action"] not in actions:
            app["actions"].extend(actions)

        if not short:

            if "error" in obj:
                app["error"] = obj["error"]

            app["yaml"] = yaml.safe_dump(obj, default_flow_style=False)

        return app

class AppLP(App):

    @require_auth
    @require_kube
    def get(self):

        apps = []

        for obj in [app.obj for app in pykube.KlotIOApp.objects(kube()).filter()]:

            apps.append(self.to_dict(obj, short=True))

        return {self.plural: sorted(apps, key=lambda app: app["name"])}

    @require_auth
    @require_kube
    def post(self):

        if "name" not in flask.request.json:
            return {"error": "missing name"}, 400

        if "source" not in flask.request.json:
            return {"error": "missing source"}, 400

        obj = {
            "apiVersion": "klot.io/v1",
            "kind": "KlotIOApp",
            "metadata": {
                "name": flask.request.json["name"],
            },
            "source": flask.request.json["source"]
        }

        if "action" in flask.request.json:
            obj["action"] = flask.request.json["action"]

        pykube.KlotIOApp(kube(), obj).create()

        return {"message": f"{obj['metadata']['name']} queued"}, 202

class AppRIU(App):

    @staticmethod
    def nodes(nodes):

        for node in [node.obj for node in pykube.Node.objects(kube()).filter()]:
            nodes.append({
                "name": node["metadata"]["name"],
                "role": "Master" if node["metadata"]["name"] == platform.node() else "Worker",
                "labels": node["metadata"]["labels"]
            })

        nodes.sort(key=operator.itemgetter('role', 'name'))

    @classmethod
    def node(cls, app, field, nodes):

        if not nodes:
            cls.nodes(nodes)

        field.options = []

        if field.multi:
            field.original = []

        for node in nodes:

            field.options.append(node["name"])

            if node["labels"].get(f"{app}/{field.name}") == field.content["node"]:
                if field.multi:
                    field.original.append(node["name"])
                else:
                    field.original = node["name"]

    @staticmethod
    def calendar(field):

        # https://www.googleapis.com/auth/calendar.readonly

        # Successfully installed cachetools-4.1.0 google-auth-1.14.0 google-auth-httplib2-0.0.3 google-auth-oauthlib-0.4.1 httplib2-0.17.2 oauthlib-3.1.0 pyasn1-modules-0.2.8 requests-oauthlib-1.3.0 rsa-4.0

        # 4/ywEX3hVZgLcTCxzQf9qAMRS_GJTLEhMtDfhTpeNCACYZWAVl31ecVho

        ready = False

        subfields = [
            {
                "name": "credentials",
                "description": "\n".join([
                    "Go to the Link below.",
                    "Create a new project.",
                    "Enable Calendar API.",
                    "Create credentials (OAuth, Other).",
                    "Download the JSON and paste it above."
                ]),
                "link": {
                    "name": "Google API's",
                    "url": "https://console.developers.google.com/apis/"
                }
            }
        ]

        credentials = json.loads(field.value['credentials']) if field.value and field.value.get("credentials") else {}

        if credentials and "token" not in credentials:

            if not field.value.get("code"):

                flow = google_auth_oauthlib.flow.Flow.from_client_config(
                    credentials,
                    scopes=['https://www.googleapis.com/auth/calendar.readonly'],
                    redirect_uri='urn:ietf:wg:oauth:2.0:oob'
                )

                url, state = flow.authorization_url(prompt='consent',access_type='offline',include_granted_scopes='true')

                credentials["state"] = state

                subfields.append({
                    "name": "code",
                    "description": "\n".join([
                        "Go to the Link below.",
                        "Click Advanced.",
                        "Authorise access to your Calendars.",
                        "Copy the Code and paste it above."
                    ]),
                    "link": {
                        "name": "Authorize Calendar Access",
                        "url": url
                    }
                })

            else:

                flow = google_auth_oauthlib.flow.Flow.from_client_config(
                    credentials,
                    scopes=['https://www.googleapis.com/auth/calendar.readonly'],
                    redirect_uri='urn:ietf:wg:oauth:2.0:oob',
                    state=credentials['state']
                )

                flow.fetch_token(code=field.value["code"])

                credentials = json.loads(flow.credentials.to_json())

        if credentials and "token" in credentials:

            service = googleapiclient.discovery.build(
                'calendar', 'v3', credentials=google.oauth2.credentials.Credentials(**credentials)
            )

            options = []
            labels = {}
            page_token = None

            while True:

                calendar_list = service.calendarList().list(pageToken=page_token).execute()

                for calendar in calendar_list['items']:
                    options.append(calendar['id'])
                    labels[calendar['id']] = calendar["summary"]

                page_token = calendar_list.get('nextPageToken')

                if not page_token:
                    break

            subfields.append({
                "name": "watch",
                "description": "The Calendar you'd like to watch.",
                "options": options,
                "labels": labels
            })

            ready = True

        field.fields = opengui.Fields(field.value, field.original, subfields)

        if credentials:
            field.fields["credentials"].value = json.dumps(credentials)

        return ready

    @classmethod
    def fields(cls, obj, values):

        fields = opengui.Fields(values, obj.get("settings", {}), obj["spec"].get("settings", []), ready=True)

        nodes = []

        for field in fields:

            if field.content.get("node"):
                cls.node(obj["metadata"]["name"], field, nodes)

            if field.content.get("google") == "calendar":
                fields.ready = fields.ready and cls.calendar(field)

        return fields

    @require_auth
    @require_kube
    def get(self, name):

        obj = pykube.KlotIOApp.objects(kube()).filter().get(name=name).obj

        return {self.singular: self.to_dict(obj)}

    @require_auth
    @require_kube
    def patch(self, name):

        if "action" not in flask.request.json:
            return {"error": "missing action"}, 400

        obj = pykube.KlotIOApp.objects(kube()).filter().get(name=name).obj

        obj["action"] = flask.request.json["action"]

        if "error" in obj:
            del obj["error"]

        pykube.KlotIOApp(kube(), obj).replace()

        return {self.singular: self.to_dict(obj)}

    @require_auth
    @require_kube
    def options(self, name):

        obj = pykube.KlotIOApp.objects(kube()).filter().get(name=name).obj

        values = flask.request.json.get("values", obj.get("settings", {}))

        fields = self.fields(obj, values)

        if values and flask.request.json.get("validate") and not fields.validate():
            return {"fields": fields.to_list(), "ready": fields.ready, "errors": fields.errors}
        else:
            return {"fields": fields.to_list(), "ready": fields.ready}

    @require_auth
    @require_kube
    def put(self, name):

        if "values" not in flask.request.json:
            return {"error": "missing config"}, 400

        obj = pykube.KlotIOApp.objects(kube()).filter().get(name=name).obj

        fields = self.fields(obj, flask.request.json["values"])

        if not fields.validate():
            return {"fields": fields.to_list(), "errors": fields.errors}, 400

        obj["settings"] = fields.values

        for field in fields:

            if not field.content.get("node") or field.value == field.original:
                continue

            label = f"{obj['metadata']['name']}/{field.name}"

            if field.multi:
                current = field.value or []
                original = field.original or []
            else:
                current = [field.value] if field.value else []
                original = [field.original] if field.original else []

            for value in current:
                if value not in original:

                    node = pykube.Node.objects(kube()).get(name=value).obj
                    node["metadata"]["labels"][label] = field.content["node"]
                    pykube.Node(kube(), node).replace()

                    if obj["status"] == "Installed":
                        obj["status"] = "Installing"

            for value in original:
                if value not in current:
                    node = pykube.Node.objects(kube()).get(name=value).obj
                    del node["metadata"]["labels"][label]
                    pykube.Node(kube(), node).replace()

        if obj["status"] == "NeedSettings":
            obj["status"] = "Installing"

        pykube.KlotIOApp(kube(), obj).replace()

        config = pykube.ConfigMap.objects(kube()).filter(namespace=obj["spec"]["namespace"]).get(name="config").obj
        config.setdefault("data", {})
        config["data"]["settings.yaml"] = yaml.safe_dump(flask.request.json["values"])
        pykube.ConfigMap(kube(), config).replace()

        return {"values": flask.request.json["values"]}

    @require_auth
    @require_kube
    def delete(self, name):

        obj = pykube.KlotIOApp.objects(kube()).filter().get(name=name).obj

        if "status" in obj and obj["status"] == "Installed":
            return {"error": f"Can't delete Installed {name}. Uninstall first."}

        pykube.KlotIOApp(kube(), obj).delete()

        return {"message": f"{name} deleted"}, 201

class AppV(App):

    @staticmethod
    def tags(source, stable=True):

        options = []
        labels = {}

        for release in requests.get(f"https://api.github.com/repos/{source['repo']}/releases").json():

            if release["prerelease"] == stable:
                continue

            label = [release["tag_name"]]

            if release.get("name"):
                label.append(release["name"])

            if release.get("body"):
                label.append(release["body"])

            options.append(release["tag_name"])
            labels[release["tag_name"]] = " - ".join(label)

        return sorted(options, reversed=True), labels

    @staticmethod
    def branches(source):

        options = []

        for branch in requests.get(f"https://api.github.com/repos/{source['repo']}/branches").json():
            if branch["name"] != "master":
                options.append(branch["name"])

        return sorted(options, reversed=True)

    @classmethod
    def fields(cls, obj, values):

        fields = opengui.Fields(values, {}, [
            {
                "name": "release",
                "options": [
                    "current"
                ],
                "labels": {
                    "current": "The most recent confirmed version (recommended)"
                },
                "trigger": True
            }
        ], ready=False)


        if obj["source"].get("site") == "github.com":
            fields["release"].options.extend([
                "stable",
                "experimental",
                "development"
            ])
            fields["release"].content["labels"].update({
                "stable": "Past confirmed versions",
                "experimental": "Unconfirmed versions (not recommended)",
                "development": "Versions currently in development (here be dragons)"
            })

        if fields["release"].value == "current":

            fields.ready = True

        elif fields["release"].value:

            fields.append({
                "name": "version"
            })

            if fields["release"].value in ["stable", "experimental"]:

                (
                    fields["version"].options,
                    fields["version"].content["labels"]
                ) = cls.tags(obj["source"], stable=(fields["release"].value == "stable"))

            elif fields["release"].value == "development":

                fields["version"].options = cls.branches(obj["source"])

            fields.ready = True

        return fields

    @require_auth
    @require_kube
    def options(self, name):

        obj = pykube.KlotIOApp.objects(kube()).filter().get(name=name).obj

        values = flask.request.json.get("values", {})

        fields = self.fields(obj, values)

        if values and flask.request.json.get("validate") and not fields.validate():
            return {"fields": fields.to_list(), "ready": fields.ready, "errors": fields.errors}
        else:
            return {"fields": fields.to_list(), "ready": fields.ready}

    @require_auth
    @require_kube
    def put(self, name):

        if "values" not in flask.request.json:
            return {"error": "missing config"}, 400

        obj = pykube.KlotIOApp.objects(kube()).filter().get(name=name).obj

        fields = self.fields(obj, flask.request.json["values"])

        if not fields.validate():
            return {"fields": fields.to_list(), "errors": fields.errors}, 400

        obj["upgrade"] = {
            "action": flask.request.json["action"]
        }

        if fields["release"].value != "current":
            obj["upgrade"]["version"] = fields["version"].value

        obj["action"] = "Upgrade"

        pykube.KlotIOApp(kube(), obj).replace()

        return {self.singular: self.to_dict(obj)}
