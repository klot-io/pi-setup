ACCOUNT=klotio
IMAGE=pi-setup
VERSION?=0.1
VOLUMES=-v ${PWD}/requirements.txt:/opt/klot-io/requirements.txt \
        -v ${PWD}/etc/:/opt/klot-io/etc/\
        -v ${PWD}/lib/:/opt/klot-io/lib/ \
        -v ${PWD}/www/:/opt/klot-io/www/ \
        -v ${PWD}/bin/:/opt/klot-io/bin/ \
        -v ${PWD}/config/:/opt/klot-io/config/ \
        -v ${PWD}/service/:/opt/klot-io/service/ \
        -v ${PWD}/images/:/opt/klot-io/images/
PORT=8083


.PHONY: build shell boot daemon convert 

build:
	docker build . -f Dockerfile.setup -t $(ACCOUNT)/$(IMAGE)-setup:$(VERSION)

shell:
	docker run --privileged=true -it --network=host $(VARIABLES) $(VOLUMES) $(ACCOUNT)/$(IMAGE)-setup:$(VERSION) sh

boot:
	docker run --privileged=true -it --rm -v /Volumes/boot/:/opt/klot-io/boot/ $(VOLUMES) $(ACCOUNT)/$(IMAGE)-setup:$(VERSION) sh -c "bin/boot.py $(VERSION)"

api:
	scp lib/manage.py pi@klot-io.local:/opt/klot-io/lib/
	ssh pi@klot-io.local "sudo systemctl restart klot-io-daemon"

daemon:
	scp lib/config.py pi@klot-io.local:/opt/klot-io/lib/
	ssh pi@klot-io.local "sudo systemctl restart klot-io-daemon"

export:
	bin/export.sh $(VERSION)

shrink:
	docker run --privileged=true -it --rm $(VOLUMES) $(ACCOUNT)/$(IMAGE):$(VERSION) sh -c "pishrink.sh images/pi-$(VERSION).img"

config:
	docker-compose -f docker-compose.yml up

clean:
	docker-compose -f docker-compose.yml down
