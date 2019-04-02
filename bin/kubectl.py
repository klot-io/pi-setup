#!/usr/bin/env python

import os
import yaml
import requests

cluster = input("cluster: ")
password = input("password: ")

remote = {}

if os.path.exists("secret/kubectl"):

    print(f"\nadding {cluster}-klot-io context\n")

    with open("secret/kubectl", "r") as config_file:

        response = requests.post(
            f"http://{cluster}-klot-io.local/api/kubectl",
            headers={"klot-io-password": password},
            json={"kubectl": yaml.safe_load(config_file)}
        )

else:

    print(f"\nusing {cluster}-klot-io context\n")

    response = requests.get(
        f"http://{cluster}-klot-io.local/api/kubectl",
        headers={"klot-io-password": password}
    )

response.raise_for_status()
config = response.json()["kubectl"]

with open("secret/kubectl", "w") as config_file:
    yaml.safe_dump(config, config_file, default_flow_style=False)
