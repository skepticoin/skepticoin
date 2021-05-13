## How does a wallet work?

* Your wallet cointains a number of "keypairs": pairs of (private, public) keys.

* The public keys can be publically communicated; they are often called "addresses", because coin can be sent to them.

* The private keys must be kept private; they can be used to unlock the coin that was transferred to the associated
  public key.

* Although a single public key could be reused for receiving coins repeatedly, this is not recommended. (mainly because
  it makes tracking coin to individuals even easier than it otherwise would be).

* Therefore, each time you call `skepticoin-receive`, or mine a new block, one of your public keys is earmarked in the
  wallet as having been used for that particular purpose.

* The wallet does not, by itself, contain coins: it only contains keypairs. When a skepticoin client reports that "your
  wallet now contains _x_ coins", what it really does is check against the blockchain which of that chain's spendable
  "transaction outputs" are unlockable by the wallet, and sum their values.

## Technical details:

* Your wallet is in a file called `wallet.json`.

* The first time you start `skepticoin`, a new wallet is automatically generated for you, with 10.000 keypairs.

* When the addresses run out, you'll get an error message; you'll have to generate some new ones manually. (This is by
  design: quietly adding new addresses in the background, as the early `bitcoin-core` client did, may lead to loss of
  coin because it is not obvious that backups of the wallet have become outdated)

* Each time a public key is earmarked for a purpose this fact is stored in your wallet.

* If you restore an old backup which misses some of these annotations, you may accidentally reuse addresses, which may
  cause loss of privacy.

* Spending coin usually also uses up a receiving address from your own wallet, which is used for the "change".
  (This is because transactions cannot spend fractions of earlier transaction outputs, so that when the amount doesn't
  match the desired amount, the surplus must be preserved as change)

* Signing transactions is done with the Elliptic Curve Digital Signature Algorithm (ECDSA), using the SECP256k1 curve.
  The choice of curve mirrors bitcoin, although the there-popular Pay-to-PubKey Hash (P2PKH) algorithm was not used.

* Addresses are rendered for human consumption by converting the 64 bytes to hexadecimal notation, prepending `"SKE"`
  and postpending `"PTI"`.

## "Security"

* There is absolutely no guarantee that running `skepticoin` will not destroy your wallet.
* If the wallet is destroyed and there is no backup the coin is lost forever.
* If an attacker gains access to the wallet, they can steal all coins from it
