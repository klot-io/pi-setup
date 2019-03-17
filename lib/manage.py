import os
import yaml
import functools

import flask
import flask_restful

def app():

    app = flask.Flask("klot-io-api")

    api = flask_restful.Api(app)

    api.add_resource(Health, '/health')
    api.add_resource(Auth, '/auth')
    api.add_resource(Config, '/config')

    return app


def require_auth(endpoint):
    @functools.wraps(endpoint)
    def wrap(*args, **kwargs):

        with open("/opt/klot-io/config/account.yaml", "r") as config_file:
            password = yaml.load(config_file)["password"]

        if "klot-io-password" not in flask.request.headers:
            return {"message": "missing password"}, 400

        if flask.request.headers["klot-io-password"] != password:
            return {"message": "invalid password"}, 401

        return endpoint(*args, **kwargs)

    return wrap

class Health(flask_restful.Resource):
    def get(self):
        return {"message": "OK"}


class Auth(flask_restful.Resource):

    def get(self):

        with open("/opt/klot-io/config/account.yaml", "r") as config_file:
            password = yaml.load(config_file)["password"]

        if "klot-io-password" not in flask.request.headers:
            return {"error": "missing password"}

        if flask.request.headers["klot-io-password"] != password:
            return {"error": "invalid password"}

        return {"message": "OK"}


class Config(flask_restful.Resource):

    name = "config"

    def settings(self, values=None):

        if values == None:
            values = {}

        settings = [
            {
                "name": "account",
                "fields": [
                    {
                        "name": "password"
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
                        "name": "cluster"
                    },
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

        if "network" in values and "interface" in values["network"] and \
           values["network"]["interface"] == "wlan0":
            settings[1]["fields"].extend([
                {
                    "name": "country"
                },
                {
                    "name": "ssid"
                },
                {
                    "name": "psk",
                    "label": "password"
                }
            ])

        if "kubernetes" in values and \
           "role" in values["kubernetes"] and values["kubernetes"]["role"] == "worker":
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

    def load(self):

        loaded = {}

        for setting in self.settings():
            if os.path.exists("/opt/klot-io/config/%s.yaml" % setting["name"]):
                with open("/opt/klot-io/config/%s.yaml" % setting["name"], "r") as config_file:
                    loaded[setting["name"]] = yaml.load(config_file)
            else:
                loaded[setting["name"]] = {}

        return loaded

    def validate(self, settings, values):

        errors = []

        for setting in settings:

            if setting["name"] not in flask.request.json[self.name]:
                errors.append("missing %s" % setting["name"])
                continue

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
