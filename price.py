import requests
from pprint import pprint

# baseid = 'CULTURE'
# quoteid = 'SOL'

# url = f'https://price.jup.ag/v6/price?ids={baseid}&vsToken={quoteid}'

# res = requests.get(url=url)

# symbols = []
# if res.ok:
#     data = res.json()['data'][baseid]
#     symbols = [data['id']]
#     pprint(data)
# else:
#     print(res.status_code)
# tokenAddreses = ','.join(symbols)

tokenAddreses = '3WXnaXnqeqF5NxyjhRosVqs4jPM8XXEVJbMmkD69pump'
# print(tokenAddreses)
dexscreener_url = f'https://api.dexscreener.com/latest/dex/tokens/{tokenAddreses}'

res = requests.get(url=dexscreener_url)

# pprint(res.json())
            # {'baseToken': {'address': '3WXnaXnqeqF5NxyjhRosVqs4jPM8XXEVJbMmkD69pump',
            #               'name': 'Men of Culture',
            #               'symbol': 'CULTURE'},
            # 'chainId': 'solana',
            # 'dexId': 'raydium',
            # 'fdv': 852110,
            # 'info': {'imageUrl': 'https://dd.dexscreener.com/ds-data/tokens/solana/3WXnaXnqeqF5NxyjhRosVqs4jPM8XXEVJbMmkD69pump.png',
            #          'socials': [{'type': 'twitter',
            #                       'url': 'https://x.com/culturectoonsol'},
            #                      {'type': 'telegram',
            #                       'url': 'https://t.me/culturecto'}],
            #          'websites': []},
            # 'liquidity': {'base': 85217787,
            #               'quote': 488.9531,
            #               'usd': 145377.24},
            # 'pairAddress': 'xkiBRjrhXuxqG3ri9gnySNVSaTN9SKp7sZjR4oZqi6F',
            # 'pairCreatedAt': 1721349302000,
            # 'priceChange': {'h1': -6.17,
            #                 'h24': -46.26,
            #                 'h6': -5.06,
            #                 'm5': -1.35},
            # 'priceNative': '0.000005727',
            # 'priceUsd': '0.0008521',
            # 'quoteToken': {'address': 'So11111111111111111111111111111111111111112',
            #                'name': 'Wrapped SOL',
            #                'symbol': 'SOL'},
            # 'txns': {'h1': {'buys': 146, 'sells': 77},
            #          'h24': {'buys': 2666, 'sells': 2303},
            #          'h6': {'buys': 279, 'sells': 262},
            #          'm5': {'buys': 1, 'sells': 6}},
            # 'url': 'https://dexscreener.com/solana/xkibrjrhxuxqg3ri9gnysnvsatn9skp7szjr4ozqi6f',
            # 'volume': {'h1': 49237.43,
            #            'h24': 859146.31,
            #            'h6': 96411.68,
            #            'm5': 118.98}}

data = res.json()['pairs'][0]

# Format message
message = f"""
Buy ${data['baseToken']['symbol']} - ({data['baseToken']['name']})
{data['baseToken']['address']}

BALANCE: 5 USDC
Price: ${data['priceUsd']} - Liq: ${data['liquidity']['usd']:.2f} - MC: ${data['fdv']:.1f}
(chg) 5m: {data['priceChange']['m5']:.2f}% - 1h: {data['priceChange']['h1']:.2f}% - 24h: {data['priceChange']['h24']:.2f}%
"""
# <- Back | Refresh
#   Swap  |  Limit  
#  10 USDC | Amount
# 1% slippage | 5% slippage
#       BUY

print(message)

# Buy $SOL - (SOLANA)
# TOKEN_MINT_ADDRESS

# BALANCE: USDC
# Price: $0.01(USDC) - Liq: 145.11K - MC: $830.5K
# (chg) 5m: 4.87% - 1h: 1.23% - 24h: -0.00%
# <- Back | Refresh
#   Swap  |  Limit  
#  10 USDC | Amount
# 1% slippage | 5% slippage
#       BUY
