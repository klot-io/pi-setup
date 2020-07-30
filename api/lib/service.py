import os
import yaml

import flask
import flask_restful

import pykube
import pykube.exceptions

def app():

    app = flask.Flask("klot-io-api")

    app.kube = pykube.HTTPClient(pykube.KubeConfig.from_service_account())

    api = flask_restful.Api(app)

    api.add_resource(Health, '/health')
    api.add_resource(Node, '/node')
    api.add_resource(Member, '/app/<string:name>/member')

    return app


class Health(flask_restful.Resource):
    def get(self):
        return {"message": "OK"}


class Node(flask_restful.Resource):

    def options(self):

        options = []
        master = None
        app = flask.request.args.get("app")
        label = flask.request.args.get("label")
        value = flask.request.args.get("value")
        workers = []

        for obj in [node.obj for node in pykube.Node.objects(flask.current_app.kube).filter()]:

            if app and label and value and obj["metadata"].get("labels", {}).get(f"{app}/{label}") != value:
                continue

            if obj["metadata"].get("labels", {}).get("node-role.kubernetes.io/master"):
                master = obj["metadata"]["name"]
            else:
                workers.append(obj["metadata"]["name"])

        if master is not None:
            options.append(master)

        options.extend(sorted(workers))

        return {"options": options}


class Member(flask_restful.Resource):

    def get(self, name):

        try:

            group = pykube.KlotIOApp.objects(flask.current_app.kube).filter().get(name=name).obj.get("spec", {}).get("group")

            members = []

            for obj in [app.obj for app in pykube.KlotIOApp.objects(flask.current_app.kube).filter()]:

                spec = obj.get("spec", {})

                if (
                    spec.get("group") and spec.get("member") and "url" in obj and
                    spec["group"] == group and obj["metadata"]["name"] != name
                ):
                    members.append({
                        "name": spec["member"],
                        "url": obj["url"]
                    })

            members.sort(key=lambda member: member["name"])

            if os.path.exists("/opt/klot-io/config/kubernetes.yaml"):

                with open("/opt/klot-io/config/kubernetes.yaml", "r") as cluster_file:
                    cluster = yaml.safe_load(cluster_file)["cluster"]

                members.append({
                    "name": "Klot I/O",
                    "url": f"http://{cluster}-klot-io.local"
                })

            return {"members": members}

        except pykube.exceptions.ObjectDoesNotExist:

            return {"message": f"{name} not found"}, 404
