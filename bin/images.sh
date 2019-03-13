#!/bin/sh

set -e

echo "installing kubernetes images"
docker pull k8s.gcr.io/kube-scheduler-arm:v1.10.2
docker pull k8s.gcr.io/kube-apiserver-arm:v1.10.2
docker pull k8s.gcr.io/kube-controller-manager-arm:v1.10.2
docker pull k8s.gcr.io/etcd-arm:3.1.12
docker pull k8s.gcr.io/pause-arm:3.1
