from peewee import SqliteDatabase, Model, CharField, IntegerField, ForeignKeyField, AutoField, BooleanField
from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, List
from datetime import datetime

db = SqliteDatabase('disciplines.db')

# Таблица категорий
class Category(Model):
    name = CharField(unique=True, max_length=100)

    class Meta:
        database = db

# Таблица дисциплин (с мягким удалением)
class Discipline(Model):
    id = AutoField()
    name = CharField(unique=True, max_length=100)
    code = CharField(unique=True, max_length=20)
    total_hours = IntegerField(constraints=[Check('total_hours > 0')])  # Ограничение на уровне БД
    category = ForeignKeyField(Category, backref='disciplines', null=False)
    is_active = BooleanField(default=True)  # Для мягкого удаления
    deleted_at = DateTimeField(null=True)  # Опционально: время удаления
    
    class Meta:
        database = db
    
    @classmethod
    def get_by_id(cls, discipline_id: int):
        """Получение дисциплины по ID (только активные)"""
        try:
            return cls.select().where(
                (cls.id == discipline_id) & (cls.is_active == True)
            ).get()
        except cls.DoesNotExist:
            return None
    
    @classmethod
    def update_by_id(cls, discipline_id: int, update_data: dict):
        """Обновление дисциплины по ID"""
        discipline = cls.get_by_id(discipline_id)
        if not discipline:
            return None
        
        # Проверка уникальности name и code при обновлении
        if 'name' in update_data:
            existing = cls.select().where(
                (cls.name == update_data['name']) & 
                (cls.id != discipline_id) & 
                (cls.is_active == True)
            ).exists()
            if existing:
                raise ValueError('Discipline with this name already exists')
        
        if 'code' in update_data:
            existing = cls.select().where(
                (cls.code == update_data['code']) & 
                (cls.id != discipline_id) & 
                (cls.is_active == True)
            ).exists()
            if existing:
                raise ValueError('Discipline with this code already exists')
        
        query = cls.update(update_data).where(cls.id == discipline_id)
        query.execute()
        return cls.get_by_id(discipline_id)
    
    @classmethod
    def delete_by_id(cls, discipline_id: int, soft_delete: bool = True):
        """
        Удаление дисциплины по ID
        soft_delete=True - мягкое удаление (только is_active=False)
        soft_delete=False - физическое удаление из БД
        """
        discipline = cls.get_by_id(discipline_id)
        if not discipline:
            return False
        
        if soft_delete:
            # Мягкое удаление
            query = cls.update(
                is_active=False, 
                deleted_at=datetime.now()
            ).where(cls.id == discipline_id)
            query.execute()
        else:
            # Физическое удаление
            query = cls.delete().where(cls.id == discipline_id)
            query.execute()
        
        return True
    
    @classmethod
    def get_active_disciplines(cls, filters=None):
        """Получение всех активных дисциплин с фильтрацией"""
        query = cls.select().where(cls.is_active == True)
        if filters:
            query = filters.apply_filters(query)
        return query

# --- Pydantic схемы для ответов ---
class DisciplineResponse(BaseModel):
    id: int
    name: str
    code: str
    total_hours: int
    category_id: int
    is_active: bool = True
    
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
        if Discipline.select().where(
            (Discipline.name == v) & (Discipline.is_active == True)
        ).exists():
            raise ValueError('Discipline with this name already exists')
        return v

    @validator('code')
    def code_unique(cls, v):
        if Discipline.select().where(
            (Discipline.code == v) & (Discipline.is_active == True)
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
    
    @root_validator
    def at_least_one_field(cls, values):
        """Проверка, что передан хотя бы один параметр для обновления"""
        if not any([values.get('name'), values.get('code'), 
                   values.get('total_hours'), values.get('category_id')]):
            raise ValueError('At least one field must be provided for update')
        return values
    
    @validator('category_id')
    def category_exists(cls, v):
        if v is not None and not Category.select().where(Category.id == v).exists():
            raise ValueError(f'Category with id {v} does not exist')
        return v

class DisciplineFilter(BaseModel):
    category_id: Optional[int] = None
    name_contains: Optional[str] = None
    code_contains: Optional[str] = None
    min_hours: Optional[int] = Field(None, ge=0)  # Изменено на ge=0
    max_hours: Optional[int] = Field(None, ge=0)  # Изменено на ge=0
    include_inactive: bool = False  # Включать ли удаленные дисциплины
    limit: int = Field(100, ge=1, le=100)
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
        # Фильтр по активности
        if not self.include_inactive:
            query = query.where(Discipline.is_active == True)
        
        if self.category_id:
            query = query.where(Discipline.category == self.category_id)
        
        # Регистронезависимый поиск
        if self.name_contains:
            query = query.where(Discipline.name.contains(self.name_contains.lower()))
        
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
    print("\nДобавлены улучшения:")
    print("✓ Ограничение total_hours > 0 на уровне БД")
    print("✓ Мягкое удаление (поле is_active)")
    print("✓ Регистронезависимый поиск")
    print("✓ Валидация min_hours/max_hours с ge=0")
    print("✓ Методы get_by_id, update_by_id, delete_by_id")
    print("✓ Возврат False при удалении несуществующей дисциплины")
    print("✓ Уникальность при обновлении с учетом ID")
