local('kubectl apply -f kubernetes/namespace.yaml')

docker_build('api-klot-io', './api')

k8s_yaml(kustomize('.'))

k8s_resource('api', port_forwards=['17584:80', '17552:5678'])