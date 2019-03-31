pi-setup
========

Setup Raspberry Pi's for Kloud of Things

WARNING:  Only do this at home on a secure network. This is by no means production ready. 

DANGER:  Always be careful downloading and installing other people's code. 

# Getting Started

Download image from <URL> and burn onto an SD card.

## Easiest

This is the easiest method, but should only be done on your own home network.

Put card into Pi.  Wire to your network (ethernet cable). Boot.

Go to http://klot-io.local/ (might take a minute to appear). 

Login with 'kloudofthings'

Set a new password. This'll be both for the interface you're using and the pi account on the Pi.

Set your network options.  This is where you can switch to wireless if you want. 

Set your cluster name and for the first one, set as master. 

Click Config.  You should have to log in with your new password. 

Watch your Status change as the Pi comes onlnie with Kuberentes

Once enabled, wire another to the network.  It should appear in the status page. 

Give it a name and network, and click Join.  You can watch it come online the Master node's status page.

## Secure

This is a little more involved but more secure. 

This just works on Mac for now.  Happy to do Windows and Linux when I have the chance.

Requirements:
- docker
- docker-compose

Pop the SD card out after burning and pop it back in.

Enable the cross compiler with `make cross`.  This allows ARM (Raspberry Pi processor) images to run on docker. 

Type `make config` in this repo and go to http://127.0.0.1:8084 when docker compose is up.

Configure this SD card, starting with the master first.  

Ctrl-C to exit and then to a `make clean` to ensure there's no residual docker images running.

Repeat for each worker SD card. Make sure you eject each SD from the Mac. 

Put the cards in the Pi's and boot up.  After a few minutes, go to http://<cluster>-klot-io.local where <cluster> is the cluster you configured.

# Apps

Once you have a master node and a few workers, head over to Apps.



# Kubectl

To integrate this new Kubernetes Cluster with your local kubectl, `make kubectl`.

It'll ask you for the cluster and password. It'll create a context for this cluster (clsuter-klot-io). 

If you have an existing `~/.kube/config` it'll merge else it'll just create a new ~/.kube/config file. 

It'll also install kubectl if you don't have it already. 

You can see if it worked by checking nodes:

```
kubectl get nodes
```

# Make your own apps

An App is just Custom Resource Definition in Kuberenetes. Adding an App for Preview is literally just creating a resource, like making Namespace or Pod.

Here's the general redis.klot.io App:

```yaml
apiVersion: klot.io/v1
kind: App
metadata:
  name: redis.klot.io
  description: Redis Server - Kloud of Things I/O
spec:
  source:
    site: github.com
    repo: klot-io/redis
  manifests:
  - path: kubernetes/namespace.yaml
  - path: kubernetes/daemon.yaml
  labels:
  - name: storage
    description: Required to place Redis
    value: enabled
    master: true
  settings:
  - name: redis
    version: "5.0.3"
    host: db.redis-klot-io
    port: 6379
```

## basics

apiVersion and kind are standard.  The metadata.name should be domain like.  The metadata.description should explain what it is.

## source

The spec.source is where it's from and is also used to load manifests.  Currently there are two formats, GitHub and URL.

### github

For GitHub, the minimal information must be site (github.com or publicly accessible GitHub server) and repo, which is just the owner/project.

Additionally you can supply version, which is a tag or branch (defaults to master), and a path to the App resource file (defaults to klot-io-app.yaml):

```yaml
spec:
  source:
    site: github.com
    repo: klot-io/redis
    version: master
    path: klot-io-app.yaml
```

### url

You can also give a straight URL which must have nothing but the App resource.  Here's the equivalent to Redis:

```yaml
spec:
  source:
    url: https://raw.githubusercontent.com/klot-io/redis/master/klot-io-app.yaml
```

## manifests

Manifests are the resources to be created when your App is installed. 

Their order doesn't matter.  The App loader simply looks at all the resources in all the manifests and creates Namespace, etc. first and then Serviccies, etc. 

Manifests are loaded by merging with this source.

### github

For example if your source is GitHub, all manifests have to specify is the relative path in the repo:

```yaml
spec:
  manifests:
  - path: kubernetes/namespace.yaml
  - path: kubernetes/daemon.yaml
```

### url

If your source is a URL, manifests need to be full URL's too:

```yaml
spec:
  manifests:
  - path: https://raw.githubusercontent.com/klot-io/redis/master/kubernetes/namespace.yaml
  - path: https://raw.githubusercontent.com/klot-io/redis/master/kubernetes/daemon.yaml
```

## labels

Labels are optional, used to ensure special services end up on the appropriate nodes. 

For example, redis.klot.io by default saves to disk.  So if a Redis Pod dies you want it to come back with that data from disk. 

Normally Pods can be created on any node, so to ensure consistency redis.klot.io requires that it's only installed on the node labeled as such:

```yaml
spec:
  labels:
  - name: storage
    description: Required to place Redis
    value: enabled
    master: true
```

The means a node has to be labeled `redis.klot.io/storage=enabled` for redis.klot.io to be installed on it.  

The master setting here means it's ok to install this on the Kubernetes master.

I often do this because I'll back my master with an SSD hard drive, so it's more durable than a regular Pi. 

You can see this in the `Deployment` in `kubernetes/daemon.yaml`

```yaml
apiVersion: extensions/v1beta1
kind: Deployment
metadata:
  name: db
  namespace: redis-klot-io
spec:
  template:
    spec:
      tolerations:
      - effect: NoSchedule
        key: node-role.kubernetes.io/master
      nodeSelector:
        redis.klot.io/storage: enabled
      volumes:
      - name: redis
        hostPath:
          path: /home/pi/storage/redis
      containers:
      - name: redis
        volumeMounts:
        - name: redis
          mountPath: /var/lib/redis
```

First, with `volumes` and `volumeMounts` we're having `/home/pi/storage/redis.klot.io` on the host machine map to `/var/lib/redis` in the Pod. If the Pod goes away and comes back, it's data will still be there. 

Second, with `nodeSelector` we're saying only this on nodes labeled with `redis.klot.io/storage=enabled` and `tolerations` we're saying this can tolerate the `NoSchedule` taint on the master. 

## settings

Settings contain the information for other Apps to interact with this one.

```yaml
spec:
  settings:
  - name: redis
    version: "5.0.3"
    host: db.redis-klot-io
    port: 6379
```

This says it's a Redis instance `name`, it's `version` 5.0.3, the `host` to connect to is db.redis-klot-io and `port` is 6379. 

You can see where this comes from in the `Service` of `kubernetes/daemon.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: db
  namespace: redis-klot-io
spec:
  ports:
  - port: 6379
    protocol: TCP
    targetPort: 6379
```

The host is from `name`.`namespace` and the port is from `port`.

# Build your own Firmware

This all completely open source.  If you want ot make your own image, go right ahead

Make sure you're on the same network as the Pi will be.

## base image

On Mac:

```
# Burn the image first then
make build
make boot
```

Pop into Pi, connect serial cable, power on, and create a console.

## enable tmpfs

Login when prompted (pi/raspberry)

```
cd /boot/klot-io/bin
./tmpfs.sh
```

Will reboot when done.

## enable wifi

This is only needed so that the Pi can download.  You don't need to do this step if you're using the the wired ethernet port.

Login when prompted (pi/raspberry)

```
cd /boot/klot-io/bin
./wifi.sh
```

Answer questions for ssid and psk. 

Will reboot when done.

## install kubernetes

Login when prompted (pi/raspberry)

```
cd /boot/klot-io/bin
./kubernetes.sh
```

Will reboot when done.

## download docker images

Login when prompted (pi/raspberry)

```
cd /boot/klot-io/bin
./images.sh
```

## install clout-io services

```
cd /boot/klot-io/bin
./klot-io.sh
```

Will install and run the config daemon and then tails its logs to make sure it's working.

The daemon sets hostname to klot-io, cange pi password to 'kloudofthings', and reset network to eth0 (if needed)

## export image to Mac

Shutdown the pi, eject the card, place into the Mac. 

```
make export
```

This will copy the SD image to the images/ directory as pi-(version>).img with (verison) from the Makefile. Fair warning, this takes for forever.

## shrink image to more manageable size

```
make shrink
```

This will shrink down images/pi-(version>).img to a more manageable size. 

# Console

```bash
screen -S pi /dev/cu.usbserial 115200
# To exit, ctrl-a, :quit and then unplug the cable
```

Can leave console going through multiple reboots of the Pi.

To disconnect, ctrl-a, :quit, and then unplugged the cable from the Mac.  Not doing this may require a hard reboot of the Mac.
