import signal
import time
import requests
import asyncio

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

TG_BOT_TOKEN = '' # @botfather
TG_CHAT_ID = '' # @userinfobot

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
        self._init_keyboard()
        self._start_thread()

    def _init_keyboard(self) -> None:
        """
        Validates the keyboard configuration from telegram config
        section.
        """
        self._keyboard = [
            ["/status"],
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
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._price),
        ]
        callbacks = [
            CallbackQueryHandler(self._update_price, pattern=r"update_price_\S+"),
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

    async def _send_msg(
        self,
        msg: str,
        parse_mode: str = ParseMode.MARKDOWN,
        keyboard = None,
        callback_path: str = "",
        reload_able: bool = False,
        query = None,
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
                    self.chat_id,
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
                    self.chat_id,
                    text=msg,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
        except TelegramError as telegram_err:
            print("TelegramError: %s! Giving up on that message.", telegram_err.message)

    async def _start(self, update: Update, context: CallbackContext):
        await self._send_msg("Welcome! Send me a token address to get its latest price information.")

    async def _status(self, update: Update, context: CallbackContext):
        await self._send_msg("Online")

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
        price_msg = await self._get_price_msg(message)
        await self._send_msg(
            f"{price_msg}",
            reload_able=True,
            callback_path=f"update_price__{message}",
            query=update.callback_query,
        )

    async def _update_price(self, update: Update, _: CallbackContext) -> None:
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
                )

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
