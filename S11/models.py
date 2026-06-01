from peewee import SqliteDatabase, Model, CharField, IntegerField, ForeignKeyField, AutoField, Check
from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, List
from contextlib import contextmanager

db = SqliteDatabase('disciplines.db')

# Таблица категорий
class Category(Model):
    name = CharField(unique=True, max_length=100)

    class Meta:
        database = db

# Таблица дисциплин (физическое удаление по умолчанию)
class Discipline(Model):
    id = AutoField()
    name = CharField(unique=True, max_length=100)
    code = CharField(unique=True, max_length=20)
    total_hours = IntegerField(constraints=[Check('total_hours > 0')])
    category = ForeignKeyField(Category, backref='disciplines', null=False)

    class Meta:
        database = db
    
    @classmethod
    def get_by_id(cls, discipline_id: int):
        """Получение дисциплины по ID"""
        try:
            return cls.select().where(cls.id == discipline_id).get()
        except cls.DoesNotExist:
            return None
    
    @classmethod
    def update_by_id(cls, discipline_id: int, update_data: dict):
        """Обновление дисциплины по ID"""
        discipline = cls.get_by_id(discipline_id)
        if not discipline:
            return None
        
        # Проверка уникальности name при обновлении
        if 'name' in update_data:
            existing = cls.select().where(
                (cls.name == update_data['name']) & 
                (cls.id != discipline_id)
            ).exists()
            if existing:
                raise ValueError('Дисциплина с таким названием уже существует')
        
        # Проверка уникальности code при обновлении
        if 'code' in update_data:
            existing = cls.select().where(
                (cls.code == update_data['code']) & 
                (cls.id != discipline_id)
            ).exists()
            if existing:
                raise ValueError('Дисциплина с таким кодом уже существует')
        
        query = cls.update(update_data).where(cls.id == discipline_id)
        query.execute()
        return cls.get_by_id(discipline_id)
    
    @classmethod
    def delete_by_id(cls, discipline_id: int):
        """
        Физическое удаление дисциплины по ID
        Возвращает True, если дисциплина была удалена, False - если не найдена
        """
        discipline = cls.get_by_id(discipline_id)
        if not discipline:
            return False
        
        query = cls.delete().where(cls.id == discipline_id)
        deleted_count = query.execute()
        return deleted_count > 0

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
        if Discipline.select().where(Discipline.name == v).exists():
            raise ValueError('Дисциплина с таким названием уже существует')
        return v

    @validator('code')
    def code_unique(cls, v):
        if Discipline.select().where(Discipline.code == v).exists():
            raise ValueError('Дисциплина с таким кодом уже существует')
        return v

    @validator('category_id')
    def category_exists(cls, v):
        if not Category.select().where(Category.id == v).exists():
            raise ValueError(f'Категория с id {v} не существует')
        return v

class DisciplineUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    code: Optional[str] = Field(None, max_length=20)
    total_hours: Optional[int] = Field(None, gt=0)
    category_id: Optional[int] = None
    
    @root_validator
    def at_least_one_field(cls, values):
        """Проверка, что передан хотя бы один параметр для обновления"""
        if not any([values.get('name'), values.get('code'), 
                   values.get('total_hours'), values.get('category_id')]):
            raise ValueError('Необходимо передать хотя бы одно поле для обновления')
        return values
    
    @validator('category_id')
    def category_exists(cls, v):
        if v is not None and not Category.select().where(Category.id == v).exists():
            raise ValueError(f'Категория с id {v} не существует')
        return v

class DisciplineFilter(BaseModel):
    category_id: Optional[int] = None
    name_contains: Optional[str] = None
    code_contains: Optional[str] = None
    min_hours: Optional[int] = Field(None, gt=0)  # Изменено на gt=0
    max_hours: Optional[int] = Field(None, gt=0)  # Изменено на gt=0
    limit: int = Field(100, ge=1)
    offset: int = Field(0, ge=0)
    
    @validator('category_id')
    def category_exists(cls, v):
        if v is not None and not Category.select().where(Category.id == v).exists():
            raise ValueError(f'Категория с id {v} не существует')
        return v
    
    @validator('max_hours')
    def max_hours_greater_than_min(cls, v, values):
        """Проверка, что max_hours >= min_hours"""
        if v is not None and values.get('min_hours') is not None:
            if v < values['min_hours']:
                raise ValueError('max_hours должно быть больше или равно min_hours')
        return v
    
    def apply_filters(self, query):
        """Применение фильтров к запросу"""
        if self.category_id:
            query = query.where(Discipline.category == self.category_id)
        
        # Регистронезависимый поиск для SQLite
        if self.name_contains:
            query = query.where(
                Discipline.name ** f'%{self.name_contains}%'  # Регистронезависимый поиск в SQLite
            )
        
        if self.code_contains:
            query = query.where(Discipline.code.contains(self.code_contains))
        
        if self.min_hours is not None:
            query = query.where(Discipline.total_hours >= self.min_hours)
        
        if self.max_hours is not None:
            query = query.where(Discipline.total_hours <= self.max_hours)
        
        query = query.limit(self.limit).offset(self.offset)
        
        return query

@contextmanager
def get_db_connection():
    """Контекстный менеджер для работы с БД"""
    db.connect()
    try:
        yield
    finally:
        db.close()

def init_db():
    with get_db_connection():
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

if __name__ == "__main__":
    init_db()
