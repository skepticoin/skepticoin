from .humans import computer

# In cryptocurrency tradition, the genesis block contains a newspaper headline that serves 2 purposes:
#
# [a] riling up the troops, i.e. convincing everyone that they're all in some kind of political project together.
# [b] proving that the blockchain is no older than a certain date (how else could you have produced the headline?).
#
# The second purpose is somewhat suspicious though, since:
#
# [1] given crypto's own set of assumptions, how long you spend calculating hashes shouldn't matter, all that matters is
#     the total (on average) of hashes being calculated.
# [2] the main threat against any crypto is not that the original creator spent some time mining coins, but that someone
#     else comes along with a _newer_ coin that's just as good or better than the old one. No newspaper headline can
#     guard against that.
#
# Thus, Scepticoin's genesis block only does [a].

just_believe_in_me = (
    b"You buy a piece of paradise\n"
    b"You buy a piece of me\n"
    b"I'll get you everything you wanted\n"
    b"I'll get you everything you need\n"
    b"Don't need to believe in hereafter\n"
    b"Just believe in me"
)

genesis_block_data = computer(
    '00000000000000000000000000000000000000000000000000000000000000000000616c35621abdf928185b74d57985cea7ff2d66ef318c58'
    'ec7ea8dd01ed089028604e7f3101000000000000000000000000000000000000000000000000000000000000000000003aea13176dbcbf6210'
    '55bdb3d6a138be4b73229d8584cb380e1dd1bbe1cedd42820000000000000000000000000000000000000000000000000000000000000000e3'
    '8ee41a6b0f6584fe8b95bd8c8d7b4d6db961fa5c2a6fafe72ea1533dd2838b0100010000000000000000000000000000000000000000000000'
    '000000000000000000000000000100000000ab596f75206275792061207069656365206f662070617261646973650a596f7520627579206120'
    '7069656365206f66206d650a49276c6c2067657420796f752065766572797468696e6720796f752077616e7465640a49276c6c206765742079'
    '6f752065766572797468696e6720796f75206e6565640a446f6e2774206e65656420746f2062656c6965766520696e20686572656166746572'
    '0a4a7573742062656c6965766520696e206d6501000000003b9aca0002aac3faad6ddc26ec4674328741498fe74bdb0d8e49a22473a02370e5'
    '3d69b0079819d5ac3f0cd36f25578eb042ad2a7b59f84a0b5f622e41ac982f478e8cb259'
)
