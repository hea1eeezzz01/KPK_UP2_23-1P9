from peewee import SqliteDatabase, Model, CharField, IntegerField, ForeignKeyField, BooleanField, AutoField
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
    id = AutoField()  # Автоматическая генерация первичного ключа
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
    category_id: int  # Возвращаем ID, хотя в модели поле category
    
    class Config:
        from_attributes = True
    
    @classmethod
    def from_orm(cls, discipline):
        """Преобразование ORM-объекта в Pydantic-схему"""
        return cls(
            id=discipline.id,
            name=discipline.name,
            code=discipline.code,
            total_hours=discipline.total_hours,
            category_id=discipline.category.id
        )

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
        # Проверка уникальности только среди НЕ удаленных дисциплин
        if Discipline.select().where(
            Discipline.name == v, 
            Discipline.is_deleted == False
        ).exists():
            raise ValueError('Discipline with this name already exists')
        return v

    @validator('code')
    def code_unique(cls, v):
        if Discipline.select().where(
            Discipline.code == v, 
            Discipline.is_deleted == False
        ).exists():
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
    
    class Config:
        # Позволяет передавать дополнительные поля (например, id для валидации)
        extra = 'allow'
    
    @validator('name')
    def name_unique(cls, v, values):
        if v:
            # Проверяем, что если передан id, то исключаем текущую запись
            discipline_id = values.get('id')
            query = Discipline.select().where(
                Discipline.name == v, 
                Discipline.is_deleted == False
            )
            if discipline_id:
                query = query.where(Discipline.id != discipline_id)
            
            if query.exists():
                raise ValueError('Discipline with this name already exists')
        return v

    @validator('code')
    def code_unique(cls, v, values):
        if v:
            discipline_id = values.get('id')
            query = Discipline.select().where(
                Discipline.code == v, 
                Discipline.is_deleted == False
            )
            if discipline_id:
                query = query.where(Discipline.id != discipline_id)
            
            if query.exists():
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
    include_deleted: bool = False  # Флаг для включения удаленных записей
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)
    
    @validator('category_id')
    def category_exists(cls, v):
        if v and not Category.select().where(Category.id == v).exists():
            raise ValueError(f'Category with id {v} does not exist')
        return v
    
    def apply_filters(self, query):
        """Применение всех фильтров к запросу"""
        # Фильтрация по удаленным записям
        if not self.include_deleted:
            query = query.where(Discipline.is_deleted == False)
        
        # Фильтр по категории
        if self.category_id:
            query = query.where(Discipline.category == self.category_id)
        
        # Регистронезависимый поиск по названию
        if self.name_contains:
            query = query.where(Discipline.name.contains(self.name_contains))
        
        # Регистронезависимый поиск по коду
        if self.code_contains:
            query = query.where(Discipline.code.contains(self.code_contains))
        
        # Фильтр по часам
        if self.min_hours is not None:
            query = query.where(Discipline.total_hours >= self.min_hours)
        
        if self.max_hours is not None:
            query = query.where(Discipline.total_hours <= self.max_hours)
        
        # Пагинация
        query = query.limit(self.limit).offset(self.offset)
        
        return query

def init_db():
    db.connect()
    # Создаем таблицы
    db.create_tables([Category, Discipline], safe=True)
    
    # Создание тестовых категорий (только если таблица пуста)
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
    print("Реляционная БД с двумя таблицами инициализирована")
