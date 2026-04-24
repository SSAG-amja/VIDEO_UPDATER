from sqlalchemy import Column, Integer, String, Text, Float, Date, BigInteger, Boolean
from models.base import Base

class Movie(Base):
    __tablename__ = "movies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tmdb_id = Column(Integer, unique=True)
    imdb_id = Column(String(50))
    title = Column(String(255))
    title_ko = Column(String(255))
    original_title = Column(String(255))
    original_language = Column(String(50))
    overview = Column(Text)
    popularity = Column(Float)
    vote_average = Column(Float)
    vote_count = Column(Integer)
    release_date = Column(Date)
    runtime = Column(Integer)
    budget = Column(BigInteger)
    revenue = Column(BigInteger)
    adult = Column(Boolean, nullable=False, default=False)
    status = Column(String(50))
    poster_path = Column(Text)
    backdrop_path = Column(Text)