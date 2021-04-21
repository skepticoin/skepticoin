## What is Scepticoin?

Scepticoin is a peer-to-peer digital currency that enables you to send money
online. It's also the central community of people who think that's bullshit.

#### What's your problem with Crypto?

Crypto-currencies are fine when viewed as a technological curiosity. If you
actually believe that blockchains are the future, that bitcoin is a store of
value, or that non-fungible tokens are anything but a scam, things get problematic.

#### Why a coin then?

Crypto-enthousiasts have an incentive to be loud about crypto-currency: the
more other people they convince, the richer they themselves become. Crypto-sceptics
are a silent majority: they have no such incentive, so you never hear them.
Scepticoin changes that, by making the sceptics invested in a coin themselves.

## Goals & motto

* 1 SC equals 1 BTC
* Not "to the moon", but "into the ground"

## Getting started

Follow the instructions below, and experience the thrill of being an early
adopter without any of the guilt of doing something that you deeply don't
believe in.

The quickstart assumes (for now) that you have Python up and running.

```
# Installing:
$ python3 -m venv .
$ . bin/activate
$ pip install --upgrade scepticoin
[..]
Successfully installed scepticoin-0.1.2 ecdsa-0.16.1 immutables-0.15 scepticoin scrypt-0.8.18 six-1.15.0

# Receving coin (copy/paste the cryptic string to someone who can send you money):
$ scepticoin-receive "I want my coin"
Created new wallet w/ 10.000 keys
SCE815dea23355609057721c08fe754efa855b50606949edb3dc300870b2c3f280115d29ea00ce76b202f7bd5fe38c917370cc8a4629a8bc10bf3e344d50d850b02PTI


# Sending coin:
$ scepticoin-send 1 scepticoin SCE815dea23355609057721c08fe754efa855b50606949edb3dc300870b2c3f280115d29ea00ce76b202f7bd5fe38c917370cc8a4629a8bc10bf3e344d50d850b02PTI
Created new directory for chain
Reading chain from disk
[..]
00019000-0130dc3498df05743b3b9a94a8543a5bb06167d7351b827312508b34bb351014
[..]
Creating new peers.json
Starting networking peer in background

NETWORK
Nr. of connected peers: 3           <= watch this to make sure your're connected to the network
  xx.xxx.xx.xxx:2412 - OUTGOING
  [..]

CHAIN
Height    ...
Date/time 2021-03-22T13:36:16       <= watch this bit to get a sense of how the blockchain download is coming along

[.. the above repeats for a while ..]

Chain up to date
Broadcasting transaction on the network Transaction #...........
Monitoring...
Transaction confirmed at .... with 0 confirmation blocks

# Mining
$ scepticoin-mine

[.. similar to the above ..]

Waiting for fresh chain
Starting mining
FOUND 000xxxxx-000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx <= this displays the height and hash of what you just found
Your wallet now contains 2730 scepticoin                                        <= this is where you start dreaming of a lambo
```

Note that scepticoin's scripts will create whatever files they need to operate
right in the directory where they're being called. This includes your wallet.

## Get coin

Scepticoin is a "early phase" coin. This means you can probably mine some yourself, as per the instructions above.

If you have ethical objections against this, you can always go to the
[faucet](https://github.com/scepticoin/scepticoin/issues/1) to get some free coin.

## Frequently Asked Questions

**Q:** Is this is real coin?

**A:** Scepticoin is every bit as real as Bitcoin and its many clones.

##

**Q:** Is this some kind of joke?

**A:** You can laugh all you want, but we all know you're just trying to hide your fear of missing out.

##

**Q:** Isn't this basically Dogecoin?

**A:** No. Dogecoin started as a fun and friendly internet coin, but it didn't take long before it got completely overrun
       by money-hungrey speculators of the worst kind. Scepticoin was founded on a firm disbelief in cryptocurrency. Whether
       it will be completely overrun by speculators remains to be seen.

##

**Q:** Is it safe to put my life savings into scepticoin?

**A:** [No](docs/security.md)

## Commonly raised objections

**O:** I can't buy scepticoin at an exchange -- this means it's not a "real" coin!

**A:** You have that exactly backwards: Scepticoin is a peer-to-peer digital currency, which means it's independent from
       established financial institutions such as exchanges. This independence is precisely its strength! You aren't
       trying to suggest that cryptocurrency's main claim to fame is untrue, are you?

##

**O**: If you're so against cryptocurrency, starting a coin of your own is hypocritical.

**A**: The ability to hold 2 directly opposing thoughts in your head is the core of cryptocurrency. If you can't do that
       then this indeed isn't for you.
