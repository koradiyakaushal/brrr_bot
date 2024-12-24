import threading
from contextvars import ContextVar
from typing import Final, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from models import BotUser, ModelBase, Wallet

DEFAULT_DB_URL = "sqlite:///bot.sqlite"
REQUEST_ID_CTX_KEY: Final[str] = "request_id"
_request_id_ctx_var: ContextVar[Optional[str]] = ContextVar(REQUEST_ID_CTX_KEY, default=None)

def get_request_or_thread_id() -> Optional[str]:
    """
    Helper method to get either async context (for fastapi requests), or thread id
    """
    request_id = _request_id_ctx_var.get()
    if request_id is None:
        # when not in request context - use thread id
        request_id = str(threading.current_thread().ident)

    return request_id


def init_db(db_url: str = DEFAULT_DB_URL, clean_open=False) -> None:
    """
    Initializes the database
    :param db_url: Database url
    :param clean_open: Clean open (will remove database on open)
    """
    kwargs = {}

    if clean_open and db_url.startswith('sqlite'):
        import os
        try:
            os.remove(db_url.replace('sqlite:///', ''))
        except FileNotFoundError:
            pass

    if db_url.startswith('sqlite'):
        kwargs.update({
            'connect_args': {'check_same_thread': False},
        })

    engine = create_engine(db_url, future=True, **kwargs)

    BotUser.session = scoped_session(
        sessionmaker(bind=engine, autoflush=False), scopefunc=get_request_or_thread_id
    )
    Wallet.session = scoped_session(
        sessionmaker(bind=engine, autoflush=False), scopefunc=get_request_or_thread_id
    )
    ModelBase.metadata.create_all(engine)


def cleanup_db() -> None:
    """
    Flushes all pending operations to disk.
    :return: None
    """
    BotUser.session.flush()
