from sqlalchemy import Column, Integer, String
from models.base import Base

class Ott(Base):
    __tablename__ = "otts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tmdb_id = Column(Integer, unique=True)
    name = Column(String(50), unique=True, nullable=False)
    name_ko = Column(String(100), unique=True, nullable=False)

class Genre(Base):
    __tablename__ = "genres"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tmdb_id = Column(Integer, unique=True)
    name = Column(String(50), unique=True, nullable=False)
    name_ko = Column(String(100), unique=True, nullable=False)

class Person(Base):
    __tablename__ = "people"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tmdb_id = Column(Integer, unique=True)
    name = Column(String(100), nullable=False)
    name_ko = Column(String(100), nullable=True)# 임시로 한글 이름은 nullable로 설정 (추후 데이터 보강 시 수정 가능)

class Keyword(Base):
    __tablename__ = "keywords"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tmdb_id = Column(Integer, unique=True)
    name = Column(String(100), unique=True, nullable=False)