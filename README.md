# unicrypto

uniCrypto parses files (or folders, recursively) for cryptocurrency addresses. Parsed addresses are submitted to a crypto API which returns basic information such as current balance and transactional information, which is then compiled with other metadata into a JSON file saved at the root of the target directory (unless another output location is specified).

```
usage: unicrypto.py [-h] [-e] -i [I]

parse files or folders [recursively] for crypto addresses!

optional arguments:
  -h, --help           show this help message and exit
  -e, --enrich         perform API lookup of BTC, BCH, and ETH address(es)
  -i [I], --input [I]  file or folder to be parsed

currently supported coins: btc, bch, eth, ltc, doge, dash, xmr, neo, xrp
```

