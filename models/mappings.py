from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from models.base import Base

class MovieGenre(Base):
    __tablename__ = "movie_genres"
    
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    genre_id = Column(Integer, ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True)

class MovieOtt(Base):
    __tablename__ = "movie_otts"
    
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    ott_id = Column(Integer, ForeignKey("otts.id", ondelete="CASCADE"), primary_key=True)
    is_streaming = Column(Boolean, default=False)
    is_rent = Column(Boolean, default=False)
    is_buy = Column(Boolean, default=False)

class MovieKeyword(Base):
    __tablename__ = "movie_keywords"
    
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id", ondelete="CASCADE"), primary_key=True)

class MovieActor(Base):
    __tablename__ = "movie_actors"
    
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    actor_id = Column(Integer, ForeignKey("people.id", ondelete="CASCADE"), primary_key=True)
    cast_name = Column(String(100))

class MovieDirector(Base):
    __tablename__ = "movie_directors"
    
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    director_id = Column(Integer, ForeignKey("people.id", ondelete="CASCADE"), primary_key=True)