ACCOUNT=klotio
IMAGE=pi-setup
VERSION?=0.2
VOLUMES=-v ${PWD}/boot_requirements.txt:/opt/klot-io/requirements.txt \
        -v ${PWD}/etc/:/opt/klot-io/etc/\
        -v ${PWD}/lib/:/opt/klot-io/lib/ \
        -v ${PWD}/www/:/opt/klot-io/www/ \
        -v ${PWD}/bin/:/opt/klot-io/bin/ \
        -v ${PWD}/config/:/opt/klot-io/config/ \
        -v ${PWD}/kubernetes/:/opt/klot-io/kubernetes/ \
        -v ${PWD}/service/:/opt/klot-io/service/ \
        -v ${PWD}/images/:/opt/klot-io/images/ \
		-v ${PWD}/secret/:/opt/klot-io/secret/ \
		-v ${PWD}/clusters/:/opt/klot-io/clusters/
PORT=8083
KLOTIO_HOST?=klot-io.local


.PHONY: cross build shell boot cluster update export shrink zip config clean kubectl tag untag

cross:
	docker run --rm --privileged multiarch/qemu-user-static:register --reset

build:
	docker build . -f Dockerfile.setup -t $(ACCOUNT)/$(IMAGE)-setup:$(VERSION)

shell:
	docker run --privileged=true -it --network=host $(VARIABLES) $(VOLUMES) $(ACCOUNT)/$(IMAGE)-setup:$(VERSION) sh

boot:
	docker run --privileged=true -it --rm -v /Volumes/boot/:/opt/klot-io/boot/ $(VOLUMES) $(ACCOUNT)/$(IMAGE)-setup:$(VERSION) sh -c "bin/boot.py $(VERSION)"

cluster:
	docker run -it --network=host $(VARIABLES) $(VOLUMES) $(ACCOUNT)/$(IMAGE)-setup:$(VERSION) sh -c "bin/cluster.py"

update:
	docker run -it --network=host $(VARIABLES) $(VOLUMES) $(ACCOUNT)/$(IMAGE)-setup:$(VERSION) sh -c "bin/update.py"

export:
	bin/export.sh $(VERSION)

shrink:
	docker build . -f Dockerfile.shrink -t $(ACCOUNT)/$(IMAGE)-shrink:$(VERSION)
	docker run --privileged=true -it --rm $(VOLUMES) $(ACCOUNT)/$(IMAGE)-shrink:$(VERSION) sh -c "pishrink.sh images/pi-$(VERSION).img"

zip:
	rm -f images/pi-$(VERSION).img.zip
	zip -9v images/pi-$(VERSION).img.zip images/pi-$(VERSION).img

config:
	cp config/*.yaml /Volumes/boot/klot-io/config/
	docker-compose -f docker-compose.yml build
	docker-compose -f docker-compose.yml up

clean:
	docker-compose -f docker-compose.yml down

kubectl:
ifeq (,$(wildcard /usr/local/bin/kubectl))
	curl -LO https://storage.googleapis.com/kubernetes-release/release/v1.10.2/bin/darwin/amd64/kubectl
	chmod +x ./kubectl
	sudo mv ./kubectl /usr/local/bin/kubectl
endif
	mkdir -p secret
	rm -f secret/kubectl
	[ -f ~/.kube/config ] && cp ~/.kube/config secret/kubectl || [ ! -f ~/.kube/config ]
	docker run -it $(VARIABLES) $(VOLUMES) $(ACCOUNT)/$(IMAGE)-setup:$(VERSION) bin/kubectl.py
	mv secret/kubectl ~/.kube/config

tag:
	-git tag -a "v$(VERSION)" -m "Version $(VERSION)"
	git push origin --tags

untag:
	-git tag -d "v$(VERSION)"
	git push origin ":refs/tags/v$(VERSION)"
