from datetime import datetime
from sqlalchemy import (Column, Integer, String, Text, DateTime, Boolean, ForeignKey,
                        Table, CheckConstraint, UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
class Timestamp:
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
class User(Base, Timestamp):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
class Home(Base, Timestamp):
    __tablename__ = "homes"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    owner_id = Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    cache_version = Column(Integer, nullable=False, server_default="1")
class Location(Base, Timestamp):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True)
    home_id = Column(ForeignKey("homes.id", ondelete="RESTRICT"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False, server_default="space")
    parent_id = Column(ForeignKey("locations.id", ondelete="RESTRICT"), index=True)
    __table_args__ = (CheckConstraint("parent_id IS NULL OR parent_id <> id"),)
class Category(Base, Timestamp):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    home_id = Column(ForeignKey("homes.id"), nullable=False)
    name = Column(String(100), nullable=False)
class Tag(Base, Timestamp):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    home_id = Column(ForeignKey("homes.id"), nullable=False)
    name = Column(String(100), nullable=False)
    __table_args__ = (UniqueConstraint("home_id", "name"),)
class Item(Base, Timestamp):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    home_id = Column(ForeignKey("homes.id", ondelete="RESTRICT"), nullable=False, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=False, server_default="")
    location_id = Column(ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False, index=True)
    category_id = Column(ForeignKey("categories.id", ondelete="RESTRICT"))
    quantity = Column(Integer, nullable=False, server_default="1")
    last_confirmed_at = Column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("quantity >= 1"),)
item_tags = Table("item_tags", Base.metadata,
    Column("item_id", ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True))
class Photo(Base):
    __tablename__ = "item_photos"
    id = Column(Integer, primary_key=True)
    item_id = Column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(300), nullable=False)
    is_cover = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
class History(Base):
    __tablename__ = "item_location_history"
    id = Column(Integer, primary_key=True)
    item_id = Column(ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    from_location_id = Column(ForeignKey("locations.id", ondelete="RESTRICT"))
    to_location_id = Column(ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False)
    moved_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    note = Column(Text, nullable=False, server_default="")
