## What is Skepticoin?

Skepticoin is a peer-to-peer digital currency that enables you to send money
online. It's also the central community of people who think that's bullshit.

#### What's your problem with Crypto?

Crypto-currencies are fine when viewed as a technological curiosity. If you
actually believe that blockchains are the future, that bitcoin is a store of
value, or that non-fungible tokens are anything but a scam, things get problematic.

#### Why a coin then?

Crypto-enthousiasts have an incentive to be loud about crypto-currency: the
more other people they convince, the richer they themselves become. Crypto-sceptics
are a silent majority: they have no such incentive, so you never hear them.
Skepticoin changes that, by making the sceptics invested in a coin themselves.

## Goals & motto

* 1 SC equals 1 BTC
* Not "to the moon", but "into the ground"

## Getting started

Follow the instructions below, and experience the thrill of being an early
adopter without any of the guilt of doing something that you deeply don't
believe in.

The quickstart assumes (for now) that you have Python up and running. _The instructions below are written with
Linux/POSIX in mind._

* If you're a MacOS user, it is presumed that you have installed python3 yourself somehow (e.g. using pyenv).
* If you're a Windows user, remember to use `Scripts\activate.bat` instead of `.bin/activate`.

```
# Installing:
$ python3 -m venv .
$ . bin/activate
$ pip install --upgrade skepticoin
[..]
Successfully installed skepticoin-0.1.2 ecdsa-0.16.1 immutables-0.15 skepticoin scrypt-0.8.18 six-1.15.0

# Receving coin (copy/paste the cryptic string to someone who can send you money):
$ skepticoin-receive "I want my coin"
Created new wallet w/ 10.000 keys
SKE815dea23355609057721c08fe754efa855b50606949edb3dc300870b2c3f280115d29ea00ce76b202f7bd5fe38c917370cc8a4629a8bc10bf3e344d50d850b02PTI


# Sending coin:
$ skepticoin-send 1 skepticoin SKE815dea23355609057721c08fe754efa855b50606949edb3dc300870b2c3f280115d29ea00ce76b202f7bd5fe38c917370cc8a4629a8bc10bf3e344d50d850b02PTI
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
$ skepticoin-mine

[.. similar to the above ..]

Waiting for fresh chain
Starting mining
FOUND 000xxxxx-000xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx <= this displays the height and hash of what you just found
Your wallet now contains 2730 skepticoin                                        <= this is where you start dreaming of a lambo
```

Note that skepticoin's scripts will create whatever files they need to operate
right in the directory where they're being called. This includes your wallet.

## Get coin

Skepticoin is a "early phase" coin. This means you can probably mine some yourself, as per the instructions above.

If you have ethical objections against this, you can always go to the
[faucet](https://github.com/skepticoin/skepticoin/issues/1) to get some free coin.

## Frequently Asked Questions

**Q:** Is this is real coin?

**A:** Skepticoin is every bit as real as Bitcoin and its many clones.

##

**Q:** Is this some kind of joke?

**A:** You can laugh all you want, but we all know you're just trying to hide your fear of missing out.

##

**Q:** Isn't this basically Dogecoin?

**A:** No. Dogecoin started as a fun and friendly internet coin, but it didn't take long before it got completely overrun
       by money-hungrey speculators of the worst kind. Skepticoin was founded on a firm disbelief in cryptocurrency. Whether
       it will be completely overrun by speculators remains to be seen.

##

**Q:** Is it safe to put my life savings into skepticoin?

**A:** [No](https://github.com/skepticoin/skepticoin/blob/master/docs/security.md)

##

**Q:** Is this some kind of get rich quick scheme?

**A:** If you're asking you're probably looking for one. If you're buying skepticoin in the hope that some greater fool
       will buy them from you at a higher price, just know that, on average, it's likely that you're the greatest fool.

## Commonly raised objections

**O:** I can't buy skepticoin at an exchange -- this means it's not a "real" coin!

**A:** You have that exactly backwards: Skepticoin is a peer-to-peer digital currency, which means it's independent from
       established financial institutions such as exchanges. This independence is precisely its strength! You aren't
       trying to suggest that cryptocurrency's main claim to fame is untrue, are you?

##

**O**: If you're so against cryptocurrency, starting a coin of your own is hypocritical.

**A**: The ability to hold 2 directly opposing thoughts in your head is the core of cryptocurrency. If you can't do that
       then this indeed isn't for you.

##

**O**: This thing is fugly and way too technical. It will never gain traction among a sufficiently large group of fools
       without a pretty GUI.

**A**: Patience, young grasshopper, everything at its time. First we bring in the techies who bring their thorough
       understanding of crypto-nonsense and steadfast determination to bring it all down to the ground. The tech
       illiterate are only allowed to join the lower ranks of the pyramid, so that GUI must wait a bit.

## Getting involved

The best places to find other Skeptics are

* [The Skepticoin Subreddit](https://www.reddit.com/r/skepticoin/) (use [old.reddit.com to avoid the popup on
  mobile](https://old.reddit.com/r/skepticoin/) if you don't have a Reddit account.)

* [Twitter](https://twitter.com/Skepticoinz)

## Contributing:

Some ways you can contribute to this project:

* Spread the news. ([Remember the first principle](https://github.com/skepticoin/skepticoin/blob/master/docs/philosophy/principles.md))
* [Set up port forwarding on your router](https://github.com/skepticoin/skepticoin/blob/master/docs/port-forwarding.md)
* [File a bug](https://github.com/skepticoin/skepticoin/issues/new) if you have one
* Open a PR (but make sure to read
  [CONTRIBUTING.md](https://github.com/skepticoin/skepticoin/blob/master/CONTRIBUTING.md) first
