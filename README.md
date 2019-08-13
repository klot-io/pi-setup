# What is this Krazy Thang?

Kloud of Things I/O is a Kubernetes cloud running on Raspberry Pi’s with the ability to download and install Apps that can utilize the I/O hardware of those Pi’s.  

## What goal it solves

Klot I/O lowers the barrier of entry to many relevant technologies (Docker, Kubernetes, REST, Python, GPIO) by allowing someone with no knowledge to easily setup said technologies in their own home. 

## Why solving it this way is

### hard

Setting up and using Docker, Kubernetes, REST, Python, GPIO is hard for someone not having regular exposure to these technologies. Each technology requires patience and diligence to get started and comes with many usage possibilities with only a subset of those possibilities overlapping in coherent, functional manner. 

### good

Klot I/O is contained on a single image that when installed onto Raspberry Pi’s, creates a localized website (and some other services) that makes connecting those Pi’s to each other and installing pre-existing Apps as simple as filling out forms and clicking buttons. From there, users can dive deeper, from accessing Kubernetes directly, to poking around the various microservices, to writing and deploying their own microservices on Kubernetes, to even writing and sharing their own Apps for others to use.

### preventing

Klot I/O mainly prevents the infrastructure problem pets over cattle. While it is more than possible to setup Kubernetes locally with minikube and even Docker, it’s not in the true spirit of Kubernetes which is made to run on multiple independent nodes that can be pulled in and swapped out as necessary. Creating multiple nodes with Raspberry Pi’s from the same image is more in line with that Kubernetes overall goal as well as the goal to treat infrastructure as cattle, not pets.  Since all Pi’s have the same base image and all differences are managed by Klot I/O and Kubernetes, no Pi is special and can be pulled in and swapped out as necessary. This makes maintaining the cluster much easier than say looking up HOWTO pages and trying to remember what worked and what didn’t each time you get a new Pi or an SD card dies. 

## Recommendations

Currently, Klot I/O is not production ready and not secure outside a protected network. It is best used by hobbyists looking to create advanced home automation and applications.  It should not be on a publicly accessible network or with publicly exposed devices. Eventually, Klot I/O will become more secure but not yet. 

## More Info

[Main site](http://www.klot.io)

Wondering how all this happened?  Check out [Backstory](http://www.klot.io/#/backstory)

If you're curious on how it all work, head over to [Overview](http://www.klot.io/#/overview).

To see all the nitty gritty details, hit up [Architecture](http://www.klot.io/#architecture).

Ready to get started? Hit up [Install](Install.md) for how.

Once running, you can install Apps from repos I created in GitHub. Right now, I just have the Redis service, but I'm looking to add more. Check out [Apps](Apps.md) for more.

To see what the system can do, give [GUI](GUI.md) a gander.

Wanna play too?  Awesome! [Development](Development.md) is for you.
