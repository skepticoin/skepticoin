# Skepticoin mining

The concept of mining is the core innovation that Skepticoin capitalizes on. Before we explore what mining _is_, let's
first explore why it is needed.

To do this, we must first focus on some of the core problem that any crypto currency faces:

* where do the coins come from?
* where does the supposed value in the coins come from?

For crypto's worst enemy, _fiat currency_, the answers are simple:

* the government prints the money or licences some party to do so.
* people believe the money has value because the government holds all the power: they can put you in
  jail if you refuse to pay your taxes.

If you're not the government, you could still print honest "money" by printing IOUs. Beer tokens at the bar work
because the value enters the system when the tokens are bought for fiat, and because people believe that the barman will
accept them for beer. The same holds for their digital equivalent, gift cards.

But what if you have nothing of value, such as beer, to offer? Could you still create a coin and get people to trade it
amongst themselves as if it had value? Baseball cards come to mind as the next step on the ladder. People buy baseball
cards because they like baseball. But because the rights to print these cards are in the hands of a few, the supply can
be artificially restricted, and prices will rise as a consequence. This in turn leads to others to enter the game in
the belief that these cards represent an investment, which leads to further price increases etc. etc.

The core challenge is thus to replicate the success of baseball cards, but without:

* a central authority with powers of any kind
* a counter-party to hold accountable for an IOU
* anything that's actually worth collecting for its own sake

The core insight of ~~Bitcoin~~ Skepticoin is that this is possible, as long as:

* you have a mechanism to artificially restrict supply. (simple economics)
* there is no central authority that prints all the money; instead this ability is distributed. (this allows you to take
  on centralized money printers as the enemy as if you weren't a money printer yourself)

## What is mining?

So how can we artificially restrict supply, while the ability to print money is decentralized? This is where mining
comes in.

The basics are simple:

* we define some arbitrary puzzle for computers to solve
* whoever solves the puzzle gets some amount of coin awarded
* the difficulty of the puzzles is automatically tuned such that the number of coins matches our desired scarcity

This is explained in a bit more detail in the below.

The solving of arbitrary puzzles by computers is called "Proof of Work" in the literature, although Proof of Waste
would have been more apt, because nothing of value is produced.

The trick is usually that some [cryptographic hash function](https://en.wikipedia.org/wiki/Cryptographic_hash_function)
over the latest block in the [blockchain](https://en.wikipedia.org/wiki/Blockchain) must produce a value lower than a
certain threshold. A small piece of the latest block (the `nonce`, and the `random_data`) can be manipulated freely to
serve as an input in this guessing game.

As to the reward for guessing correctly, this is simply determined in advance. In the case of skepticoin solving the
puzzle [yields 10 coin](params.md). A common trick to increase scarcity is to have this reward decrease over time.
Skepticoin has adopted the Bitcoin trick of reducing the reward by half roughly every 4 years.

Finally, there's the automatic adjustment of difficulty of the puzzles. This is done by comparing the rate of solved
puzzles over a preceding time period with some set objective, and then changing the target threshold for the hash
accordingly. For skepticoin this is done every 10,080 blocks, or approximately 2 weeks.

## What's wrong with mining?

The problem with mining is that it puts a reward on doing useless work. Once people start trading skepticoin for real
money (TM), this puts an actual reward on mining.

Since the cost of mining (at scale) is mostly constrained by energy consumption, simple economics dictate that the
energy usage will more or less correspond with this potential reward. (It will in general be slightly below it, because
other costs factor in as well, and miners will want to make a profit too).

For bitcoin, the [The Cambridge Bitcoin Electricity Consumption Index](https://cbeci.org/) tries to put a number on this
madness with a more sophisticated model. In Februari 2021 the associated headline was that Bitcoin consumes 'more
electricity than Argentina'; if bitcoin prices continue to rise, it is easy to predict the next headline.

### The official explanation: security

The official explanation for mining is less cynical than the above for obvious reasons. Cryptocurrency enthousiasts
will tell you that Proof of Work solves the problem of providing consensus about a global ledger in a distributed
network. The reasoning is as follows: because each block on the blockchain is "signed" using a very costly mechanism,
it is infeasable to create your own fake version of the blockchain without incurring more cost than the rest of the
miners combined. In this story, the miners are simply rewarded for the work that they put in for the network as a whole.

At face value, there's not much to be said against this, except that:

* It assumes that the problem of a fully distributed global ledger with distributed consensus is worth solving in the
  first place.
* It ignores the prohibitive cost for this "solution".
* It ignores all other forms of (non-technical) consensus that already exist within the Bitcoin community. If Bitcoiners
  can generally agree about "what is bitcoin", why wouldn't they be able to agree on a ledger?

Most importantly, however, it ignores the _real value of mining_, which is: the ability to have a decentralized
mechanism for printing money, while maintaining some desired level of scarcity.

## Conclusion

Mining is bad. [Start mining today](../README.md).
