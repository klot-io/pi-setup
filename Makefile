ACCOUNT=cloudofthingsio
IMAGE=pi-setup
VERSION?=0.1
VOLUMES=-v ${PWD}/requirements.txt:/opt/clot-io/requirements.txt \
        -v ${PWD}/lib/:/opt/clot-io/lib/ \
        -v ${PWD}/bin/:/opt/clot-io/bin/ \
        -v ${PWD}/config/:/opt/clot-io/config/ \
        -v ${PWD}/service/:/opt/clot-io/service/ \
        -v ${PWD}/images/:/opt/clot-io/images/

.PHONY: build shell boot daemon convert 

build:
	docker build . -f Dockerfile.firmware -t $(ACCOUNT)/$(IMAGE)-firmware:$(VERSION)

shell:
	docker run --privileged=true -it --network=host $(VARIABLES) $(VOLUMES) $(ACCOUNT)/$(IMAGE)-firmware:$(VERSION) sh

boot:
	docker run --privileged=true -it --rm -v /Volumes/boot/:/opt/clot-io/boot/ $(VOLUMES) $(ACCOUNT)/$(IMAGE)-firmware:$(VERSION) sh -c "bin/boot.py $(VERSION)"

daemon:
	scp bin/daemon.py pi@clot-io.local:/opt/clot-io/bin/
	ssh pi@clot-io.local "sudo systemctl restart clot-io-daemon"

export:
	bin/export.sh $(VERSION)

shrink:
	docker run --privileged=true -it --rm $(VOLUMES) $(ACCOUNT)/$(IMAGE):$(VERSION) sh -c "pishrink.sh images/pi-k8s-$(VERSION).img"

firmware: build git secret base install install convert export shrink

