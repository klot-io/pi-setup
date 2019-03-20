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
        local = requests.post(
            f"http://{cluster}-klot-io.local/api/kubectl",
            headers={"klot-io-password": password},
            json={"kubectl": yaml.load(config_file)}
        ).json()

else:

    print(f"\nusing {cluster}-klot-io context\n")

    local = requests.get(
        f"http://{cluster}-klot-io.local/api/kubectl",
        headers={"klot-io-password": password}
    ).json()

with open("secret/kubectl", "w") as config_file:
    yaml.safe_dump(local, config_file, default_flow_style=False)
