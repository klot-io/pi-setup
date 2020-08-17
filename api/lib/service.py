"""
Module for the Klot I/O API
"""

# pylint: disable=no-self-use

import os
import yaml

import flask
import flask_restful

import pykube
import pykube.exceptions

import klotio
import klotio_flask_restful

def build():
    """
    Builds the Flask App
    """

    app = flask.Flask("klot-io-api")

    app.kube = pykube.HTTPClient(pykube.KubeConfig.from_service_account())

    api = flask_restful.Api(app)

    api.add_resource(klotio_flask_restful.Health, '/health')
    api.add_resource(Node, '/node')
    api.add_resource(Member, '/app/<string:name>/member')

    app.logger = klotio.logger(app.name)

    app.logger.debug("init")

    return app


class Node(flask_restful.Resource):
    """
    Handles Noddoe queries
    """

    def options(self):
        """
        OPTIONS endpoint, get nodes tagged for an App
        """

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
    """"
    Gets members for a group
    """

    def get(self, name):
        """
        GET endpoints, get other members of a group
        """

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
