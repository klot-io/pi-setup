#!/usr/bin/env python

import os
import yaml
import requests

cluster = input("cluster: ")
password = input("password: ")

remote = {}

klotio = requests.Session()
klotio.headers.update({"x-klot-io-password": password})

if os.path.exists("secret/kubectl"):

    print(f"\nadding {cluster}-klot-io context\n")

    with open("secret/kubectl", "r") as config_file:

        response = klotio.post(
            f"http://{cluster}-klot-io.local/api/kubectl",
            json={"kubectl": yaml.safe_load(config_file)}
        )

else:

    print(f"\nusing {cluster}-klot-io context\n")

    response = klotio.get(
        f"http://{cluster}-klot-io.local/api/kubectl"
    )

response.raise_for_status()
config = response.json()["kubectl"]

with open("secret/kubectl", "w") as config_file:
    yaml.safe_dump(config, config_file, default_flow_style=False)
