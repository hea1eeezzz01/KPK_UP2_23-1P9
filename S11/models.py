from peewee import SqliteDatabase, Model, CharField, IntegerField, ForeignKeyField, AutoField
from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, List

db = SqliteDatabase('disciplines.db')

# Таблица категорий
class Category(Model):
    name = CharField(unique=True, max_length=100)

    class Meta:
        database = db

# Таблица дисциплин (без мягкого удаления - физическое удаление)
class Discipline(Model):
    id = AutoField()
    name = CharField(unique=True, max_length=100)
    code = CharField(unique=True, max_length=20)
    total_hours = IntegerField()
    category = ForeignKeyField(Category, backref='disciplines', null=False)

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
    total_hours: int = Field(..., gt=0)  # строго больше 0
    category_id: int

    @validator('name')
    def name_unique(cls, v):
        if Discipline.select().where(Discipline.name == v).exists():
            raise ValueError('Discipline with this name already exists')
        return v

    @validator('code')
    def code_unique(cls, v):
        if Discipline.select().where(Discipline.code == v).exists():
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
    total_hours: Optional[int] = Field(None, gt=0)  # gt=0 для обновления
    category_id: Optional[int] = None
    
    @root_validator
    def at_least_one_field(cls, values):
        """Проверка, что передан хотя бы один параметр для обновления"""
        if not any([values.get('name'), values.get('code'), 
                   values.get('total_hours'), values.get('category_id')]):
            raise ValueError('At least one field must be provided for update')
        return values
    
    @validator('name')
    def name_unique(cls, v, values):
        if v:
            # Проверка уникальности для обновления
            # ID будет передан отдельно, здесь проверяем без ID
            # Полная проверка будет в API слое с учетом ID
            pass
        return v

    @validator('code')
    def code_unique(cls, v, values):
        if v:
            # Аналогично - полная проверка в API слое
            pass
        return v

    @validator('category_id')
    def category_exists(cls, v):
        if v is not None and not Category.select().where(Category.id == v).exists():
            raise ValueError(f'Category with id {v} does not exist')
        return v

class DisciplineFilter(BaseModel):
    category_id: Optional[int] = None
    name_contains: Optional[str] = None
    code_contains: Optional[str] = None
    min_hours: Optional[int] = Field(None, gt=0)  # gt=0, а не ge=0
    max_hours: Optional[int] = Field(None, gt=0)  # gt=0, так как часы >0
    limit: int = Field(100, ge=1, le=100)  # максимальное значение = 100 согласно документации
    offset: int = Field(0, ge=0)
    
    @validator('category_id')
    def category_exists(cls, v):
        if v is not None and not Category.select().where(Category.id == v).exists():
            raise ValueError(f'Category with id {v} does not exist')
        return v
    
    @validator('max_hours')
    def max_hours_greater_than_min(cls, v, values):
        """Проверка, что max_hours >= min_hours"""
        if v is not None and values.get('min_hours') is not None:
            if v < values['min_hours']:
                raise ValueError('max_hours must be greater than or equal to min_hours')
        return v
    
    def apply_filters(self, query):
        """Применение фильтров к запросу"""
        if self.category_id:
            query = query.where(Discipline.category == self.category_id)
        
        if self.name_contains:
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
