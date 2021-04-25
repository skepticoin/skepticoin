## Security

Skepticoin shares the following key security property with bitcoin:

Transactions are irreversible. In case of fraud or outright theft the party that has (potentially involuntarily) spent
their coin cannot reclaim it in any way. Rember though that when seen through a different lens (that of the criminal),
this is actually a strength!

[There are many more security issues though](https://ieeexplore.ieee.org/document/8369416)

## Unique risks of skepticoin

The following security properties are not shared with bitcoin (although aruably some are shared with a large percentage
of other cryptocurrencies):

* Skepticoin is a small coin, which was built with the explicit potential to make a lot of people angry.

* Skepticoin was built from scratch, taking bitcoin as an inspiration. With respect to security, the implication here is
  "reliving Bitcoin's history, one exploit at a time".

* Almost no energy was spent in trying to secure the code. Various potential vectors of attack are known, and marked as
  such with TODOs in the source code. The main reason for this was ~~lazyness~~ an efficient allocation of scarce
  development resources.

### Intentionally insecure

The lack of attention for security in skepticoin serves to prove a more fundamental point though: good security for
skepticoin users is about as important to skepticoin-the-movement as good odds for individual gamblers are for casinos.

Some examples:

* The more coin is lost, the higher the value of the remaining coin ("deflation!")
* Each large-scale hack or loss of coin that makes the news is a way to draw attention to the coin, and such news
  articles invariably focus on the value of skepticoin.

With regards to attacks on the network itself, remember that we can always betray our core principles in case of
emergency. A 51% attack can be simply refuted by blessing one fork over another (centralization), DDOS attacks can be
refuted by falling back on whitelists of known-good peers etc.

Remember: the technobabble only serves to draw in new "enthousiasts". What matters is that sceptics stay sceptical. If
we do that we can survive any attack.
