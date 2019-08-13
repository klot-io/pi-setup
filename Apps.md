# Apps! Apps! Apps!

Make sure you have a Master node and a Worker or two before installing Apps. Head back to [Install](Install.md) for how. Else hit up the Apps page on your Master.

In the future, I'll have a bunch of Apps. 
For now there's just Nandy Speech and Redis (well there's a ton more I just haven't writtend docs for them). 
Nandy Speech allows you hook up some speakers to your Pi and make it say stuff, even in various accents. 
It'll be used by the forthcoming Nandy Chore to yell at you or your kids to do stuff.  
Redis is a general Redis server which can be used by other Apps, like Nandy Speech in this case.

## Download
    
- Go to the Apps page.</li>
- Select GitHub.</li>
- Enter 'nandy-io/speech' in owner/project field.</li>
- Click the Install button.</li>
- In 10-20 seconds, Nandy Speech and Redis will appear in the Apps listing, prepping to be installed.</li>
    </ol>

### Labels

Some Apps require that you label nodes.
In some cases, it's so the App knows which Nodes have special equipment attached, like speakers for Nandy Speech.
In other cases, it's just for consistency.  So if a part of the App suddenly dies, it'll come back on the same Node, like with Redis.
The App's page allows you to set these labels easily with checkboxes.

- Click the Redis App.</li>
- Click a checkbox under labels to place it on a specfic Node (required).</li>
- It will be automatically saved.</li>
- You can uncheck a checkbox to remvoe a label.</li>
- Go back to Apps.</li>
- Click the Nandy App.</li>
- Click a checkbox under labels to tell it which Nodes have speakers attached (you can use headphones for now).</li>


For you Kubernetes savy folks, yes this is labeling Nodes through traditional Kubernetes. 
It'll prefix the actual labels with the app name. 
So `storage` is really `redis.klot.io/storage` and 'speakers' is really `speech.nandy.io/speakers`. 
    </p>

## Install

After labelling, head over to the Pods page to watch the Pods come up.
Once they're all up, head back to Apps, and click Open in the Nandy Speech App.
Type something (preferably inappropriate) and listen to your own shenanigans.

## Great Success

Congrats! You now have Nandy Speech (and a Redis server) running in your home cluster!

Yep, that's a URL on your local network based on the App and Service name. 
For you Kubernetes savy folks, yes nginx serving the site on each node also acts as a distributed Ingress controller using LoadBalancer Service definitions.
For anyone wondering how the hell the DNS is working, we're using that same Service to register CNAMES through avahi / mDNS.  Neat huh?

## Uzbeki Blues

If you're on Windows, the URL of the Apps might now work.  If you're on an Android tablet, accessing the Apps probably won't work at all. We're using mDNS here and it's not fully supported on Windows/Android in some cases. 

Fortunately, we have a way around it, if you're done with some network settings. 

- Figure out the IP of your Master node
- Go into your device's network DNS settings 
- Replace the DNS servers with the IP for your Master node

NOTE: You best keep your Master node running for that device to work properly, whether you're using Klot I/O or not. 

That's because the Master node of Klot I/O acts as a DNS server, serving our special mDNS records through regualr DNS, and passing everything else through to 8.8.8.8 (Google's DNS). So while your errants devices can't use mDNS, we can fake them out a little.
