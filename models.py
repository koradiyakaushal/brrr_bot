import logging
# from collections import defaultdict
# from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
# from math import isclose
from typing import Any, ClassVar, Dict, List, Optional, Sequence, cast

from sqlalchemy import (
    DateTime,
    Enum,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    ScalarResult,
    Select,
    String,
    UniqueConstraint,
    desc,
    func,
    select,
)
from sqlalchemy.orm import Mapped, lazyload, mapped_column, relationship, validates, DeclarativeBase, Session, scoped_session

SessionType = scoped_session[Session]


class ModelBase(DeclarativeBase):
    pass


logger = logging.getLogger(__name__)


class BotUser(ModelBase):

    __tablename__ = 'bot_users'
    __allow_unmapped__ = True
    session: ClassVar[SessionType]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, unique=True)
    username: Mapped[str] = mapped_column(String(255), nullable=True, default='')
    first_name: Mapped[str] = mapped_column(String(255), nullable=True, default='')
    last_name: Mapped[str] = mapped_column(String(255), nullable=True, default='')
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    last_interaction = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    wallets: Mapped[List["Wallet"]] = relationship("Wallet", back_populates="user")

    def __repr__(self):
        return (f'BotUser(id={self.id}, chat_id={self.chat_id}, '
                f'username={self.username}, first_name={self.first_name}, last_name={self.last_name})')

    def to_json(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'chat_id': self.chat_id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'created_at': self.created_at.isoformat(),
            'last_interaction': self.last_interaction.isoformat(),
        }

    @staticmethod
    def from_json(json_data: Dict[str, Any]) -> 'BotUser':
        return BotUser(
            chat_id=json_data['chat_id'],
            username=json_data.get('username'),
            first_name=json_data.get('first_name'),
            last_name=json_data.get('last_name'),
        )

    @staticmethod
    def get_by_chat_id(chat_id: int) -> 'BotUser':
        return BotUser.session.query(BotUser).filter(BotUser.chat_id == chat_id).first()

    def update(self, data: Dict[str, Any]) -> None:
        for key, value in data.items():
            setattr(self, key, value)
        self.session.commit()

    @staticmethod
    def commit():
        BotUser.session.commit()

    @staticmethod
    def rollback():
        BotUser.session.rollback()

    def delete(self) -> None:
        BotUser.session.delete(self)
        BotUser.commit()


class Wallet(ModelBase):
    __tablename__ = 'wallets'
    __allow_unmapped__ = True
    session: ClassVar[SessionType]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    botuser_id: Mapped[int] = mapped_column(Integer, ForeignKey('bot_users.id'))
    address: Mapped[str] = mapped_column(String(255))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # Add this line
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    last_updated = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["BotUser"] = relationship("BotUser", back_populates="wallets")

    __table_args__ = (UniqueConstraint('botuser_id', 'address', name='uq_botuser_address'),)

    def __repr__(self):
        return f'Wallet(id={self.id}, botuser_id={self.botuser_id}, address={self.address}, is_default={self.is_default})'

    def to_json(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'botuser_id': self.botuser_id,
            'address': self.address,
            'is_default': self.is_default,
            'created_at': self.created_at.isoformat(),
            'last_updated': self.last_updated.isoformat(),
        }

    @staticmethod
    def from_json(json_data: Dict[str, Any]) -> 'Wallet':
        return Wallet(
            botuser_id=json_data['botuser_id'],
            address=json_data['address'],
        )

    @staticmethod
    def get_by_botuser_and_address(botuser_id: int, address: str) -> 'Wallet':
        return Wallet.session.query(Wallet).filter(
            Wallet.botuser_id == botuser_id,
            Wallet.address == address
        ).first()

    @staticmethod
    def get_default_wallet(botuser_id: int) -> Optional['Wallet']:
        return Wallet.session.query(Wallet).filter(
            Wallet.botuser_id == botuser_id,
            Wallet.is_default == True
        ).first()

    def set_as_default(self) -> None:
        # Set all wallets for this user to non-default
        Wallet.session.query(Wallet).filter(
            Wallet.botuser_id == self.botuser_id
        ).update({Wallet.is_default: False})
        
        # Set this wallet as default
        self.is_default = True
        Wallet.session.commit()

    @staticmethod
    def add_wallet(botuser_id: int, address: str, set_default: bool = False) -> 'Wallet':
        new_wallet = Wallet(botuser_id=botuser_id, address=address)
        Wallet.session.add(new_wallet)
        
        if set_default or Wallet.session.query(Wallet).filter(Wallet.botuser_id == botuser_id).count() == 1:
            new_wallet.set_as_default()
        else:
            Wallet.session.commit()
        
        return new_wallet

    def update(self, data: Dict[str, Any]) -> None:
        for key, value in data.items():
            setattr(self, key, value)
        self.session.commit()

    @staticmethod
    def commit():
        Wallet.session.commit()

    @staticmethod
    def rollback():
        Wallet.session.rollback()

    def delete(self) -> None:
        Wallet.session.delete(self)
        Wallet.commit()
