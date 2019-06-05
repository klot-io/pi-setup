#!/usr/bin/env python

import glob
import yaml

import develop

clusters = [cluster_path.split("/")[-1].split('.')[0] for cluster_path in glob.glob("clusters/*.yaml")]

if not clusters:
    exit("no clusters defined")

if len(clusters) == 1:
    cluster = clusters[0]
else:
    cluster = input(f"cluster: [{', '.join(clusters)}]")

with open(f"clusters/{cluster}.yaml", "r") as cluster_file:
    config = yaml.safe_load(cluster_file)

nodes = [f"{cluster}-klot-io.local"]

nodes.extend([f"{worker}-{cluster}-klot-io.local" for worker in config["workers"]])

for node in nodes:

    print(node)

    deploy = develop.Deploy(node, config["password"])

    deploy.update("klot-io-daemon", "lib/config.py")
    deploy.update("klot-io-api", "lib/manage.py")
    deploy.update("nginx", "www")

    deploy.close()
