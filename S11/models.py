from peewee import SqliteDatabase, Model, CharField, IntegerField, ForeignKeyField, BooleanField, AutoField
from pydantic import BaseModel, Field, validator
from typing import Optional, List

db = SqliteDatabase('disciplines.db')

# Таблица категорий
class Category(Model):
    name = CharField(unique=True, max_length=100)

    class Meta:
        database = db

# Таблица дисциплин с мягким удалением (техническая реализация)
class Discipline(Model):
    id = AutoField()
    name = CharField(unique=True, max_length=100)
    code = CharField(unique=True, max_length=20)
    total_hours = IntegerField()
    category = ForeignKeyField(Category, backref='disciplines', null=False)
    is_deleted = BooleanField(default=False)  # Техническое поле для soft delete

    class Meta:
        database = db

# --- Pydantic схемы для ответов (строго по документации) ---
class DisciplineResponse(BaseModel):
    id: int
    name: str
    code: str
    total_hours: int
    category_id: int  # Возвращаем ID категории, как указано в документации
    
    class Config:
        from_attributes = True

class CategoryResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

# --- Pydantic схемы для запросов (строго по документации) ---
class CategoryCreate(BaseModel):
    name: str = Field(..., max_length=100)

class DisciplineCreate(BaseModel):
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=20)
    total_hours: int = Field(..., gt=0)
    category_id: int

    @validator('name')
    def name_unique(cls, v):
        # Проверка уникальности только среди активных (не удаленных) дисциплин
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
    
    # НЕ используем extra='allow' - строгое соответствие документации
    
    @validator('name')
    def name_unique(cls, v, values):
        if v:
            # Для валидации уникальности при обновлении нужен id дисциплины
            # Он будет передан отдельно в функцию обновления, не через схему
            # Здесь мы не можем проверить уникальность, т.к. нет id
            # Проверка будет в API слое
            pass
        return v

    @validator('code')
    def code_unique(cls, v, values):
        if v:
            # Аналогично - проверка в API слое
            pass
        return v

    @validator('category_id')
    def category_exists(cls, v):
        if v is not None and not Category.select().where(Category.id == v).exists():
            raise ValueError(f'Category with id {v} does not exist')
        return v
    
    def has_fields(self) -> bool:
        """Проверка, что передан хотя бы один параметр для обновления"""
        return any([
            self.name is not None,
            self.code is not None,
            self.total_hours is not None,
            self.category_id is not None
        ])

class DisciplineFilter(BaseModel):
    category_id: Optional[int] = None
    name_contains: Optional[str] = None
    code_contains: Optional[str] = None
    min_hours: Optional[int] = Field(None, ge=0)
    max_hours: Optional[int] = Field(None, ge=0)
    limit: int = Field(100, ge=1)  # Без верхнего ограничения, но с проверкой на положительность
    offset: int = Field(0, ge=0)
    
    @validator('category_id')
    def category_exists(cls, v):
        if v is not None and not Category.select().where(Category.id == v).exists():
            raise ValueError(f'Category with id {v} does not exist')
        return v
    
    def apply_filters(self, query):
        """Применение фильтров к запросу (только активные записи)"""
        # По умолчанию и всегда исключаем удаленные записи
        query = query.where(Discipline.is_deleted == False)
        
        if self.category_id:
            query = query.where(Discipline.category == self.category_id)
        
        if self.name_contains:
            # Регистронезависимый поиск
            query = query.where(Discipline.name.contains(self.name_contains))
        
        if self.code_contains:
            query = query.where(Discipline.code.contains(self.code_contains))
        
        if self.min_hours is not None:
            query = query.where(Discipline.total_hours >= self.min_hours)
        
        if self.max_hours is not None:
            query = query.where(Discipline.total_hours <= self.max_hours)
        
        query = query.limit(self.limit).offset(self.offset)
        
        return query

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
    print("Реляционная БД с двумя таблицами инициализирована")
