import requests
from pprint import pprint
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TokenAccountOpts
import asyncio

WALLET_ADDRESS = Pubkey.from_string('F5YZJ47MALsVDMfb1vDiUjuYGbvwHqJH8TeP3yLJ2w4f')
SOLANA_RPC_URL = 'https://api.mainnet-beta.solana.com'  # Add this line
SPL_TOKEN_PROGRAM_ID = TokenAccountOpts(program_id=Pubkey.from_string('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'))
USDC_ID = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
DUST_AMOUNT_IN_USD = 1

def token_prices_from_jup(holdings: list):
    token_ids = [holding['mint'] for holding in holdings]
    token_ids_str = ','.join(token_ids)
    url = f'https://price.jup.ag/v6/price?ids={token_ids_str}&vsToken={USDC_ID}'
    res = requests.get(url=url)
    return res.json()

def holdings_to_usd(holdings: list, token_prices: dict):
    new_holdings = []
    total_usd = 0.0
    for holding in holdings:
        holding['name'] = token_prices[holding['mint']]['mintSymbol']
        holding['usd_value'] = holding['amount'] * token_prices[holding['mint']]['price']
        if holding['usd_value'] < DUST_AMOUNT_IN_USD:
            continue
        total_usd += holding['usd_value']
        new_holdings.append(holding)

    new_holdings.sort(key=lambda x: x['usd_value'], reverse=True)
    return new_holdings, total_usd

def format_msg(wallet_address: str, holdings: list, total_usd: float):
    msg = ''
    msg += f"Wallet: `{wallet_address}`\n"
    msg += f"Balance: *${total_usd:.2f}*\n\n"
    for holding in holdings:
        msg += f"{holding['name']}: {holding['amount']:.2f} (${holding['usd_value']:.2f})\n"
    return msg

async def _get_spl_token_holdings(wallet_address: str):
    async with AsyncClient(SOLANA_RPC_URL) as client:
        response = await client.is_connected()
        if not response:
            return "Failed to connect to Solana RPC"

        holdings = []
        response = await client.get_token_accounts_by_owner_json_parsed(wallet_address, SPL_TOKEN_PROGRAM_ID)
        data = response.value
        for account in data:
            parsedAccountInfo = account.account.data.parsed
            mintAddress = parsedAccountInfo["info"]["mint"]
            tokenBalance = parsedAccountInfo["info"]["tokenAmount"]["uiAmount"]
            if tokenBalance > 0:
                holdings.append({'mint': mintAddress, 'amount': tokenBalance})

        token_prices = token_prices_from_jup(holdings)
        holdings_usd = holdings_to_usd(holdings, token_prices['data'])
        pprint(format_msg(wallet_address, holdings_usd[0], holdings_usd[1]))

asyncio.run(_get_spl_token_holdings(WALLET_ADDRESS))
