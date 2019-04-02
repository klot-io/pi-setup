#!/usr/bin/env python

import yaml

cluster = input("cluster: ")
password = input("password: ")

workers = []

while True:
    worker = input("worker: ")
    if not worker:
        break
    workers.append(worker)

with open("clusters/%s.yaml" % cluster, "w") as cluster_file:
    yaml.safe_dump({"password": password, "workers": workers}, cluster_file, default_flow_style=False)
