import signal
import time
import requests
import asyncio
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solana.rpc.types import TokenAccountOpts

from datetime import datetime
from threading import Thread

from telegram import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TelegramError
from telegram.ext import Application, CallbackContext, CallbackQueryHandler,CommandHandler, MessageHandler, filters

from db import cleanup_db, init_db
from models import BotUser, Wallet

TG_BOT_TOKEN = '7331267172:AAGo6yfnXvmfI7KfWDhjESGCg9v-SJMIeXk'
TG_CHAT_ID = '340567015'

WALLET_ADDRESS = Pubkey.from_string('HPx7GxQjaVvox8kcBvCkUKSSh4oYm4TUeB8fXG9oGuZM')
SOLANA_RPC_URL = 'https://api.mainnet-beta.solana.com'
SPL_TOKEN_PROGRAM_ID = TokenAccountOpts(program_id=Pubkey.from_string('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'))
USDC_ID = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
DUST_AMOUNT_IN_USD = 1

def abbreviate_number(number):
    if number < 1000:
        return str(number)
    elif number < 1000000:
        return f"{number/1000:.1f}K"
    elif number < 1000000000:
        return f"{number/1000000:.1f}M"
    else:
        return f"{number/1000000000:.1f}B"

class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self._app = None
        self._loop = None
        self._keyboard = []
        init_db()
        self._init_keyboard()
        self._start_thread()

    def _init_keyboard(self) -> None:
        """
        Validates the keyboard configuration from telegram config
        section.
        """
        self._keyboard = [
            ["/status"],
            ["/positions"],
            ["/wallets"],
        ]

    def _start_thread(self):
        """
        Creates and starts the polling thread
        """
        self._thread = Thread(target=self._init, name="BrrTelegram")
        self._thread.start()

    def _init(self):
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

        self._app = self._init_telegram_app()
        self._init_handlers()

    def _init_telegram_app(self):
        return Application.builder().token(self.token).build()

    def _init_handlers(self):
        handles = [
            CommandHandler("status", self._status),
            CommandHandler("positions", self._positions),  # Add this line
            CommandHandler("wallets", self._wallets),  # Add this line
            CommandHandler("add_wallet", self._add_wallet),  # Add this line
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._price),
        ]
        callbacks = [
            CallbackQueryHandler(self._update_price, pattern=r"update_price_\S+"),
            CallbackQueryHandler(self._refresh_positions, pattern="refresh_positions"),
            CallbackQueryHandler(self._set_default_wallet, pattern=r"set_default_\d+"),
            CallbackQueryHandler(self._prompt_add_wallet, pattern="add_new_wallet"),
        ]
        print(
            "telegram is listening for following commands: %s",
            [[x for x in sorted(h.commands)] for h in handles if isinstance(h, CommandHandler)],
        )
        for handle in handles:
            self._app.add_handler(handle)
        for callback in callbacks:
            self._app.add_handler(callback)

        self._loop.run_until_complete(self._startup_telegram())
        return handles

    async def _startup_telegram(self) -> None:
        await self._app.initialize()
        await self._app.start()
        if self._app.updater:
            await self._app.updater.start_polling(
                bootstrap_retries=-1,
                timeout=20,
                drop_pending_updates=True,
            )
            while True:
                await asyncio.sleep(10)
                if not self._app.updater.running:
                    break

    async def _cleanup_telegram(self) -> None:
        await self._send_msg('Bot is shutting down...')
        if self._app.updater:
            await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        cleanup_db()

    async def cleanup(self) -> None:
        asyncio.run_coroutine_threadsafe(self._cleanup_telegram(), self._loop)
        self._thread.join()

    async def _update_msg(
        self,
        query: CallbackQuery,
        msg: str,
        callback_path: str = "",
        reload_able: bool = False,
        parse_mode: str = ParseMode.MARKDOWN,
    ) -> None:
        if reload_able:
            reply_markup = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Refresh", callback_data=callback_path)],
                ]
            )
        else:
            reply_markup = InlineKeyboardMarkup([[]])
        msg += f"\nUpdated: {datetime.now().ctime()}"
        if not query.message:
            return

        try:
            await query.edit_message_text(
                text=msg, parse_mode=parse_mode, reply_markup=reply_markup
            )
        except BadRequest as e:
            if "not modified" in e.message.lower():
                pass
            else:
                print("TelegramError: %s", e.message)
        except TelegramError as telegram_err:
            print("TelegramError: %s! Giving up on that message.", telegram_err.message)

    async def _positions(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        username = update.effective_user.username
        first_name = update.effective_user.first_name
        last_name = update.effective_user.last_name

        bot_user = BotUser.get_by_chat_id(str(chat_id))
        if not bot_user:
            bot_user = BotUser(chat_id=str(chat_id), username=username, first_name=first_name, last_name=last_name)
            BotUser.session.add(bot_user)
        else:
            bot_user.last_interaction = datetime.utcnow()
        BotUser.commit()
        print(bot_user)

        await self._send_msg("Fetching SPL token positions...", chat_id=chat_id)
        message = await self._get_positions_message()
        await self._send_msg(
            message,
            reload_able=True,
            callback_path="refresh_positions",
            query=update.callback_query,
            chat_id=chat_id,
        )

    async def _get_positions_message(self):
        holdings = await self._get_spl_token_holdings(WALLET_ADDRESS)
        token_prices = self._token_prices_from_jup(holdings)
        holdings_usd, total_usd = self._holdings_to_usd(holdings, token_prices)
        return self._format_positions_msg(str(WALLET_ADDRESS), holdings_usd, total_usd)

    async def _get_spl_token_holdings(self, wallet_address: Pubkey):
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

            return holdings

    def _jup_price_api(self, token_ids: list):
        token_ids_str = ','.join(token_ids)
        url = f'https://price.jup.ag/v6/price?ids={token_ids_str}&vsToken={USDC_ID}'
        res = requests.get(url=url)
        if res.ok:
            return res.json()['data']
        else:
            print(f"Failed to get token prices from Jup: {res.status_code}")
            print(f"Failed to get token prices from Jup: {res.text}")
            return {}

    def _token_prices_from_jup(self, holdings: list):
        token_ids = [holding['mint'] for holding in holdings]
        token_prices = {}
        for i in range(0, len(token_ids), 100):
            token_ids_chunk = token_ids[i:i+100]
            token_prices_chunk = self._jup_price_api(token_ids_chunk)
            if token_prices_chunk:
                token_prices.update(token_prices_chunk)
        return token_prices

    def _holdings_to_usd(self, holdings: list, token_prices: dict):
        new_holdings = []
        total_usd = 0.0
        for holding in holdings:
            if holding['mint'] in token_prices.keys():
                holding['name'] = token_prices[holding['mint']]['mintSymbol']
                holding['usd_value'] = holding['amount'] * token_prices[holding['mint']]['price']
                if holding['usd_value'] < DUST_AMOUNT_IN_USD:
                    continue
                total_usd += holding['usd_value']
                new_holdings.append(holding)

        new_holdings.sort(key=lambda x: x['usd_value'], reverse=True)
        return new_holdings, total_usd

    def _format_positions_msg(self, wallet_address: str, holdings: list, total_usd: float):
        msg = f"Wallet: `{wallet_address}`\n"
        msg += f"Balance: *${total_usd:.2f}*\n\n"
        for holding in holdings:
            msg += f"{holding['name']}: {holding['amount']:.2f} (*${holding['usd_value']:.2f}*)\n"
        return msg

    async def _send_msg(
        self,
        msg: str,
        parse_mode: str = ParseMode.MARKDOWN,
        keyboard = None,
        callback_path: str = "",
        reload_able: bool = False,
        query = None,
        chat_id: int = None,
    ):
        if msg is None:
            return
        if query:
            await self._update_msg(
                query=query,
                msg=msg,
                parse_mode=parse_mode,
                callback_path=callback_path,
                reload_able=reload_able,
            )
            return
        if reload_able:
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Refresh", callback_data=callback_path)]]
            )
        else:
            if keyboard is not None:
                reply_markup = InlineKeyboardMarkup(keyboard)
            else:
                reply_markup = ReplyKeyboardMarkup(self._keyboard, resize_keyboard=True)
        try:
            try:
                await self._app.bot.send_message(
                    chat_id if chat_id else self.chat_id,
                    text=msg,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            except NetworkError as network_err:
                # Sometimes the telegram server resets the current connection,
                # if this is the case we send the message again.
                print(
                    "Telegram NetworkError: %s! Trying one more time.", network_err.message
                )
                await self._app.bot.send_message(
                    chat_id if chat_id else self.chat_id,
                    text=msg,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
        except TelegramError as telegram_err:
            print("TelegramError: %s! Giving up on that message.", telegram_err.message)

    async def _start(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        await self._send_msg("Welcome! Send me a token address to get its latest price information.", chat_id=chat_id)

    async def _status(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        await self._send_msg("Online", chat_id=chat_id)

    async def _get_price_msg(self, token_address: str):
        if len(token_address) != len('A3eME5CetyZPBoWbRUwY3tSe25S6tb18ba9ZPbWk9eFJ'):
            return
        dexscreener_url = f'https://api.dexscreener.com/latest/dex/tokens/{token_address}'
        res = requests.get(url=dexscreener_url)
        if res.status_code != 200:
            return "Token not found"
        _resjson = res.json()
        if not _resjson and 'pairs' not in _resjson:
            return "Token not found"
        _pairs = _resjson['pairs']
        if not _pairs:
            return "Token not found"
        if len(_pairs) == 0:
            return "Token not found"
        data = _pairs[0]
        message = ""
        message += f"Buy *${data['baseToken']['symbol']}* - ({data['baseToken']['name']})\n"
        message += f"`{data['baseToken']['address']}`\n"
        message += "\n"
        # message += "Balance: *5.123 USDC*\n"
        message += f"Price:* ${data['priceUsd']} *- Liq:* ${abbreviate_number(data['liquidity']['usd'])}*"
        if 'fdv' in data:
            message += f" - MC:* ${abbreviate_number(float(data['fdv']))}*\n"
        else:
            message += "\n"
        message += f"5m:* {data['priceChange']['m5']:.2f}% *- 1h:* {data['priceChange']['h1']:.2f}% *- 24h:* {data['priceChange']['h24']:.2f}%*\n"
        return message

    async def _price(self, update: Update, context: CallbackContext):
        message = update.message.text
        chat_id = update.effective_chat.id
        price_msg = await self._get_price_msg(message)
        await self._send_msg(
            f"{price_msg}",
            reload_able=True,
            callback_path=f"update_price__{message}",
            query=update.callback_query,
            chat_id=chat_id,
        )

    async def _update_price(self, update: Update, _: CallbackContext) -> None:
        chat_id = update.effective_chat.id
        if update.callback_query:
            query = update.callback_query
            if query.data and "__" in query.data:
                token_address = query.data.split("__")[1].split(" ")[0]
                price_msg = await self._get_price_msg(token_address)
                await self._send_msg(
                    f"{price_msg}",
                    reload_able=True,
                    callback_path=f"update_price__{token_address}",
                    query=update.callback_query,
                    chat_id=chat_id,
                )

    async def _refresh_positions(self, update: Update, context: CallbackContext) -> None:
        query = update.callback_query
        chat_id = update.effective_chat.id
        await query.answer()
        message = await self._get_positions_message()
        await self._send_msg(
            message,
            reload_able=True,
            callback_path="refresh_positions",
            query=query,
            chat_id=chat_id,
        )

    async def _wallets(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        bot_user = BotUser.get_by_chat_id(str(chat_id))
        if not bot_user:
            await self._send_msg("You don't have any wallets registered.", chat_id=chat_id)
            return

        wallets = bot_user.wallets
        if not wallets:
            await self._send_msg("You don't have any wallets registered.", chat_id=chat_id)
            return

        message = "Your registered wallets:\n\n"
        keyboard = []
        for wallet in wallets:
            default_mark = "✅ " if wallet.is_default else ""
            message += f"{default_mark}`{wallet.address}`\n"
            keyboard.append([InlineKeyboardButton(f"Set {wallet.address[:10]}... as default", callback_data=f"set_default_{wallet.id}")])

        keyboard.append([InlineKeyboardButton("Add new wallet", callback_data="add_new_wallet")])

        await self._send_msg(message, chat_id=chat_id, keyboard=keyboard)

    async def _add_wallet(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        if not context.args:
            await self._send_msg("Please provide a wallet address. Usage: /add_wallet <address>", chat_id=chat_id)
            return

        wallet_address = context.args[0]
        bot_user = BotUser.get_by_chat_id(str(chat_id))
        if not bot_user:
            bot_user = BotUser(chat_id=str(chat_id), username=update.effective_user.username,
                               first_name=update.effective_user.first_name,
                               last_name=update.effective_user.last_name)
            BotUser.session.add(bot_user)
            BotUser.commit()

        existing_wallet = Wallet.get_by_botuser_and_address(bot_user.id, wallet_address)
        if existing_wallet:
            await self._send_msg("This wallet is already registered.", chat_id=chat_id)
            return

        new_wallet = Wallet.add_wallet(bot_user.id, wallet_address)
        await self._send_msg(f"Wallet `{wallet_address}` has been added successfully.", chat_id=chat_id)

    async def _set_default_wallet(self, update: Update, context: CallbackContext):
        query = update.callback_query
        chat_id = update.effective_chat.id
        wallet_id = int(query.data.split('_')[-1])

        bot_user = BotUser.get_by_chat_id(str(chat_id))
        if not bot_user:
            await query.answer("Error: User not found.")
            return

        wallet = Wallet.session.query(Wallet).filter(Wallet.id == wallet_id, Wallet.botuser_id == bot_user.id).first()
        if not wallet:
            await query.answer("Error: Wallet not found.")
            return

        wallet.set_as_default()
        await query.answer("Default wallet updated successfully.")
        await self._wallets(update, context)
    
    async def _prompt_add_wallet(self, update: Update, context: CallbackContext):
        query = update.callback_query
        chat_id = update.effective_chat.id
        await query.answer()
        await self._send_msg("Please use the /add_wallet command followed by the wallet address to add a new wallet. For example:\n/add_wallet 0x1234...", chat_id=chat_id)

def term_handler(signum, frame):
    raise KeyboardInterrupt()

if __name__ == '__main__':
    tg = None

    try:
        signal.signal(signal.SIGTERM, term_handler)
        tg = Telegram(TG_BOT_TOKEN, TG_CHAT_ID)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Shutting down...")
    except Exception as ex:
        print(f"Error: {str(ex)}")
    finally:
        if tg:
            print("Cleaning up Telegram bot...")
            try:
                asyncio.run(tg.cleanup())
            except Exception as e:
                print(f"Error during cleanup: {e}")
        time.sleep(10)
        print("Bot stopped.")
