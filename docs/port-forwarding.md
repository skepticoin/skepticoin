## Set up Port Forwarding

Skepticoin is a Peer to Peer network. This means the various instances of skepticoin-the-program (which we call "nodes")
talk to each other over the network.

However, not all nodes are created equal:

* **Listening nodes** accept incoming connections from all other nodes and can start outgoing connections to other
  listening nodes.
* **Non-listening nodes** don't accept incoming connections, and can only start connection to listening nodes.

If you are running skepticoin from home, you are most likely running a non-listening node. This is because you have been
given a single IPv4 address by your ISP, which from the perspective of the rest of the world ends at your router. Your
router does not know which device to forward incoming traffic to, so it defaults to not forwarding incoming traffic at
all. (This presumes that you at least have been given an IPv4 address from your ISP, which is true in most cases)

### Benefits

By setting up your router for "Port Forwarding", your node becomes a listening node. This is good for everyone:

* As a miner, this benefits you because it decreases the chance that blocks that you find are "orphaned" (i.e. picked up
  too late by other nodes to be included in the main chain)

* It benefits the network because it increases the connectivity and makes the network more robust.

### Set up

The basic idea is to tell your router which computer is running skepticoin. As such, you'll need the following pieces of
information:

* How to access your router, and how to get into the admin screen.
* What the internal IP address / hostname of the computer that you're running skepticoin is. (dig around on your admin
  screen a bit to figure it out)

How to then actually set up Port Forwarding differs from router to router; you'll have to look it up for your particular
brand. In any case, you'll need to configure the following:

* Protocol: TCP
* Port: 2412
