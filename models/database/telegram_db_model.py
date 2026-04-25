"""Projects DB Models."""

import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Integer, String, Float, ForeignKeyConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class TelegramDataBaseDeclarativeBase(DeclarativeBase):  # type: ignore
    """Global Telegram DB Declarative Base."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if not isinstance(other, type(self)): return NotImplemented
        return self.id == other.id


class TelegramGroupOrmEntity(TelegramDataBaseDeclarativeBase):
    """Telegram Group ORM Model."""

    __bind_key__ = 'data'
    __tablename__ = 'telegram_group'

    constructor_id: Mapped[str] = mapped_column(String(255))
    access_hash: Mapped[str] = mapped_column(String(255))
    group_username: Mapped[str] = mapped_column(String(1024), index=True)
    title: Mapped[str] = mapped_column(String(4098), index=True)

    fake: Mapped[bool] = mapped_column(Boolean)
    gigagroup: Mapped[bool] = mapped_column(Boolean)
    has_geo: Mapped[bool] = mapped_column(Boolean)
    restricted: Mapped[bool] = mapped_column(Boolean)
    scam: Mapped[bool] = mapped_column(Boolean)
    verified: Mapped[bool] = mapped_column(Boolean)

    participants_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    photo_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    photo_base64: Mapped[Optional[str]] = mapped_column(String(1024000), nullable=True)
    photo_name: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    source: Mapped[str] = mapped_column(String(255), index=True)


class TelegramMessageOrmEntity(TelegramDataBaseDeclarativeBase):
    """Telegram Message ORM Model."""

    __bind_key__ = 'data'
    __tablename__ = 'telegram_message'

    group_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    media_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    date_time: Mapped[datetime.datetime] = mapped_column(DateTime)
    message: Mapped[str] = mapped_column(String(65535))
    raw: Mapped[str] = mapped_column(String(65535)) 

    from_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    from_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    to_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_reply: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    reply_to_msg_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class TelegramMediaOrmEntity(TelegramDataBaseDeclarativeBase):
    """Telegram Media ORM Model."""

    __bind_key__ = 'data'
    __tablename__ = 'telegram_media'

    group_id: Mapped[int] = mapped_column(Integer, index=True)
    telegram_id: Mapped[int] = mapped_column(Integer, index=True)
    file_name: Mapped[str] = mapped_column(String(1024))

    extension: Mapped[str] = mapped_column(String(16))
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    date_time: Mapped[datetime.datetime] = mapped_column(DateTime)

    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)

    title: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)


class TelegramUserOrmEntity(TelegramDataBaseDeclarativeBase):
    """Telegram User ORM Model."""

    __bind_key__ = 'data'
    __tablename__ = 'telegram_user'

    is_bot: Mapped[bool] = mapped_column(Boolean)
    is_fake: Mapped[bool] = mapped_column(Boolean)
    is_self: Mapped[bool] = mapped_column(Boolean)
    is_scam: Mapped[bool] = mapped_column(Boolean)
    is_verified: Mapped[bool] = mapped_column(Boolean)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    username: Mapped[str] = mapped_column(String(1024), nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    photo_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    photo_base64: Mapped[Optional[str]] = mapped_column(String(1024000), nullable=True)
    photo_name: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    date_profilation: Mapped[datetime.datetime]= mapped_column(DateTime)
    bio : Mapped[str]= mapped_column(String(1024), nullable= True)
    group_id: Mapped[int] = mapped_column(Integer, index= True)

class TelegramProfilePicOrmEntity(TelegramDataBaseDeclarativeBase):
    __bind_key__ = 'data'
    __tablename__ = 'user_profile_pic'

    photo_id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True)
    photo_base64: Mapped[Optional[str]] = mapped_column(String(1024000), nullable=True)
    photo_name: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    id : Mapped[int] = mapped_column(Integer, nullable=False)
    date_photo:Mapped[datetime.datetime]= mapped_column(DateTime)

class TelegramMessageAIAnalysisOrmEntity(TelegramDataBaseDeclarativeBase):
    """Telegram Message AI Analysis ORM Model."""

    __bind_key__ = 'data'
    __tablename__ = 'telegram_message_ai_analysis'

    # PK autonoma della tabella AI
    ai_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # FK logica verso telegram_message (che nel tuo schema ha PK composta)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ['message_id', 'group_id'],
            ['telegram_message.id', 'telegram_message.group_id']
        ),
    )

    activity_json: Mapped[Optional[str]] = mapped_column(String(65535), nullable=True)
    attack_type_json: Mapped[Optional[str]] = mapped_column(String(65535), nullable=True)
    target_nation_json: Mapped[Optional[str]] = mapped_column(String(65535), nullable=True)

    top_activity: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    top_activity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    top_attack_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    top_attack_type_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    top_target_nation: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    top_target_nation_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    model_version: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime)