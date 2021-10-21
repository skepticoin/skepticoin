PORT = 2412

# this time doubles with each retry
TIME_TO_SECOND_CONNECTION_ATTEMPT = 10
MAX_TIME_BETWEEN_CONNECTION_ATTEMPTS = 60 * 30

# tuned for approx 60 days
MAX_CONNECTION_ATTEMPTS = int(60 * 60 * 24 * 60 / MAX_TIME_BETWEEN_CONNECTION_ATTEMPTS)

GET_PEERS_INTERVAL = 60 * 30

MAX_MESSAGE_SIZE = 32 * 1024 * 1024

MAX_IBD_PEERS = 1
IBD_PEER_TIMEOUT = 60
IBD_VALIDATION_SKIP = 1000

GET_BLOCKS_INVENTORY_SIZE = 500

SWITCH_TO_ACTIVE_MODE_TIMEOUT = 5 * 60  # if your chain is 5 minutes old, start querying for blocks actively
EMPTY_INVENTORY_BACKOFF = 60  # wait this long before asking a node about inventory again on an empty response
