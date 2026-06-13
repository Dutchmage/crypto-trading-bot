from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

Base = declarative_base()
engine = create_engine("sqlite:///trading.db", echo=False)
Session = sessionmaker(bind=engine)

class Trade(Base):
    __tablename__ = "trades"
    id            = Column(Integer, primary_key=True)
    timestamp     = Column(DateTime, default=datetime.utcnow)
    symbol        = Column(String)
    side          = Column(String)          # buy / sell
    amount        = Column(Float)
    price         = Column(Float)
    strategy      = Column(String)
    mode          = Column(String)          # paper / live
    pnl           = Column(Float, default=0.0)
    closed        = Column(Boolean, default=False)

class Position(Base):
    __tablename__ = "positions"
    id            = Column(Integer, primary_key=True)
    symbol        = Column(String, unique=True)
    entry_price   = Column(Float)
    amount        = Column(Float)
    strategy      = Column(String)
    stop_loss     = Column(Float)
    take_profit   = Column(Float)
    opened_at     = Column(DateTime, default=datetime.utcnow)
    mode          = Column(String)

class DailyStats(Base):
    __tablename__ = "daily_stats"
    id            = Column(Integer, primary_key=True)
    date          = Column(String, unique=True)
    starting_balance = Column(Float)
    realized_pnl  = Column(Float, default=0.0)
    trades_count  = Column(Integer, default=0)
    wins          = Column(Integer, default=0)
    losses        = Column(Integer, default=0)

def init_db():
    Base.metadata.create_all(engine)

def get_session():
    return Session()
