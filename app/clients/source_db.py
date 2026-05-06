"""SQLAlchemy models reflecting the existing Linkstatus source database (read + targeted writes)."""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class SourceBase(DeclarativeBase):
    pass


class Domain(SourceBase):
    __tablename__ = "domains"
    id = Column(Integer, primary_key=True, autoincrement=True)
    wp_domain = Column(String(255))


class DomLabel(SourceBase):
    __tablename__ = "domlabels"
    id = Column(Integer, primary_key=True, autoincrement=True)
    labelId = Column(Integer)
    domId = Column(Integer)


class OpenOrder(SourceBase):
    __tablename__ = "openorder"
    id = Column(Integer, primary_key=True, autoincrement=True)
    domainId = Column(Integer)
    customerId = Column(Integer)
    indexed = Column(Integer)
    deliveryDate = Column(String(255))
    addedOn = Column(String(255))
    assignToId = Column(Integer)
    description = Column(Text)
    status = Column(String(50))
    comments = Column(Text)
    wp_id = Column(Integer)
    anchor1 = Column(String(255))
    anchor2 = Column(String(255))
    anchor3 = Column(String(255))
    link1 = Column(String(500))
    link2 = Column(String(500))
    link3 = Column(String(500))
    inspirational_url = Column(String(500))
    completion_time = Column(String(50))
    is_email = Column(Integer)
    email = Column(String(255))
    addedBy = Column(Integer)
    parent_id = Column(Integer)
    language = Column(String(20))
    fixed_date = Column(String(255))
    trend = Column(String(255))
    ai_model = Column(String(100))


class Admin(SourceBase):
    __tablename__ = "admin"
    id = Column(Integer, primary_key=True, autoincrement=True)
    Name = Column(String(255))
    email = Column(String(255))


class Customer(SourceBase):
    __tablename__ = "customer"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255))
    email = Column(String(255))


def get_source_engine(url: str):
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def get_source_session(url: str) -> Session:
    engine = get_source_engine(url)
    factory = sessionmaker(bind=engine)
    return factory()
