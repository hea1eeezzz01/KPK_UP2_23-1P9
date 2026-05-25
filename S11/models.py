from peewee import SqliteDatabase, Model, CharField, IntegerField, ForeignKeyField, BooleanField
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from fastapi import HTTPException

db = SqliteDatabase('disciplines.db')

# Таблица категорий
class Category(Model):
    name = CharField(unique=True, max_length=100)

    class Meta:
        database = db

# Таблица дисциплин с мягким удалением
class Discipline(Model):
    id = IntegerField(primary_key=True)  # Явное указание PK
    name = CharField(unique=True, max_length=100)
    code = CharField(unique=True, max_length=20)
    total_hours = IntegerField()
    category = ForeignKeyField(Category, backref='disciplines', null=False)
    is_deleted = BooleanField(default=False)  # Мягкое удаление

    class Meta:
        database = db

# --- Pydantic схемы для ответов ---
class DisciplineResponse(BaseModel):
    id: int
    name: str
    code: str
    total_hours: int
    category_id: int

    class Config:
        from_attributes = True

class CategoryResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

# --- Pydantic схемы для запросов ---
class CategoryCreate(BaseModel):
    name: str = Field(..., max_length=100)

class DisciplineCreate(BaseModel):
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=20)
    total_hours: int = Field(..., gt=0)
    category_id: int

    @validator('name')
    def name_unique(cls, v):
        if Discipline.select().where(Discipline.name == v, Discipline.is_deleted == False).exists():
            raise ValueError('Discipline with this name already exists')
        return v

    @validator('code')
    def code_unique(cls, v):
        if Discipline.select().where(Discipline.code == v, Discipline.is_deleted == False).exists():
            raise ValueError('Discipline with this code already exists')
        return v

    @validator('category_id')
    def category_exists(cls, v):
        if not Category.select().where(Category.id == v).exists():
            raise ValueError(f'Category with id {v} does not exist')
        return v

class DisciplineUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    code: Optional[str] = Field(None, max_length=20)
    total_hours: Optional[int] = Field(None, gt=0)
    category_id: Optional[int] = None

    @validator('name')
    def name_unique(cls, v, values):
        if v and 'id' in values:
            if Discipline.select().where(Discipline.name == v, Discipline.id != values['id'], Discipline.is_deleted == False).exists():
                raise ValueError('Discipline with this name already exists')
        return v

    @validator('code')
    def code_unique(cls, v, values):
        if v and 'id' in values:
            if Discipline.select().where(Discipline.code == v, Discipline.id != values['id'], Discipline.is_deleted == False).exists():
                raise ValueError('Discipline with this code already exists')
        return v

    @validator('category_id')
    def category_exists(cls, v):
        if v and not Category.select().where(Category.id == v).exists():
            raise ValueError(f'Category with id {v} does not exist')
        return v

class DisciplineFilter(BaseModel):
    category_id: Optional[int] = None
    name_contains: Optional[str] = None
    code_contains: Optional[str] = None
    min_hours: Optional[int] = Field(None, ge=0)
    max_hours: Optional[int] = Field(None, ge=0)
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)

def init_db():
    db.connect()
    db.create_tables([Category, Discipline], safe=True)
    
    # Создание тестовых категорий
    if Category.select().count() == 0:
        categories = [
            "Математические дисциплины",
            "Программирование",
            "Гуманитарные дисциплины",
            "Естественно-научные дисциплины"
        ]
        for cat_name in categories:
            Category.create(name=cat_name)
    
    db.close()

if __name__ == "__main__":
    init_db()
    print("Реляционная БД с двумя таблицами инициализирована.")
