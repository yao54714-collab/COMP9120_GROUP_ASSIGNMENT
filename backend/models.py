from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Model(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)

class Login(Model):
    email: str=Field(min_length=3,max_length=254)
    password: str=Field(min_length=1,max_length=128)

class Register(Login):
    display_name: str=Field(min_length=1,max_length=100)
    phone: str=Field(min_length=5,max_length=32)

class CustomerInput(Model):
    display_name: str=Field(min_length=1,max_length=100)
    phone: str=Field(min_length=5,max_length=32)
    is_active: bool=True

class PetInput(Model):
    customer_id: int|None=None
    pet_name: str=Field(min_length=1,max_length=80)
    species: Literal['dog','cat']
    breed: str=Field(default='',max_length=100)
    birth_date: date|None=None
    sex: Literal['male','female','unknown']='unknown'
    latest_weight_kg: Decimal|None=Field(default=None,gt=0,le=200)
    care_notes: str=Field(default='',max_length=2000)
    is_active: bool=True

    @field_validator('birth_date')
    @classmethod
    def not_future(cls,value):
        from datetime import datetime
        from .config import SYDNEY
        if value and value>datetime.now(SYDNEY).date():
            raise ValueError('Date of birth cannot be in the future')
        return value

class BookingItem(Model):
    pet_id: int=Field(gt=0)
    service_id: int=Field(gt=0)

class BookingInput(Model):
    customer_id: int|None=None
    requested_start_at: datetime
    customer_note: str=Field(default='',max_length=2000)
    items: list[BookingItem]=Field(min_length=1,max_length=12)

class PlanItem(Model):
    appointment_item_id: int=Field(gt=0)
    employee_id: int=Field(gt=0)
    workstation_id: int=Field(gt=0)
    planned_start_at: datetime
    duration_minutes: int=Field(gt=0,le=480)
    agreed_price: Decimal=Field(ge=0,le=10000,decimal_places=2)

class PlanInput(Model):
    items: list[PlanItem]=Field(min_length=1,max_length=12)

class UseInput(Model):
    consumable_id: int=Field(gt=0)
    quantity: Decimal=Field(gt=0,le=100000,decimal_places=3)

class CompleteInput(Model):
    result_notes: str=Field(min_length=1,max_length=3000)
    care_notes: str=Field(default='',max_length=3000)
    weight_at_visit_kg: Decimal|None=Field(default=None,gt=0,le=200)
    consumptions: list[UseInput]=Field(default_factory=list,max_length=30)

class PaymentInput(Model):
    amount: Decimal=Field(gt=0,le=100000,decimal_places=2)
    method: Literal['cash','card','transfer']
    request_key: str=Field(min_length=8,max_length=80)

class RefundInput(Model):
    payment_id: int=Field(gt=0)
    amount: Decimal=Field(gt=0,le=100000,decimal_places=2)
    reason: str=Field(min_length=1,max_length=2000)
    request_key: str=Field(min_length=8,max_length=80)

class ServiceInput(Model):
    service_code: str=Field(min_length=1,max_length=30)
    service_name: str=Field(min_length=1,max_length=100)
    species: Literal['dog','cat']
    workstation_type: Literal['wash','groom']
    base_price: Decimal=Field(ge=0,le=10000,decimal_places=2)
    default_duration_minutes: int=Field(gt=0,le=480)
    is_active: bool=True

class EmployeeInput(Model):
    employee_code: str=Field(min_length=1,max_length=30)
    display_name: str=Field(min_length=1,max_length=100)
    staff_role: Literal['manager','receptionist','groomer']
    email: str=Field(min_length=3,max_length=254)
    password: str=Field(default='',max_length=128)
    is_active: bool=True

class SkillInput(Model):
    service_ids: list[int]=Field(default_factory=list,max_length=50)

class ShiftInput(Model):
    employee_id: int=Field(gt=0)
    starts_at: datetime
    ends_at: datetime

class StationInput(Model):
    station_code: str=Field(min_length=1,max_length=30)
    station_name: str=Field(min_length=1,max_length=100)
    workstation_type: Literal['wash','groom']
    is_active: bool=True

class ConsumableInput(Model):
    sku: str=Field(min_length=1,max_length=40)
    consumable_name: str=Field(min_length=1,max_length=100)
    base_unit: Literal['ml','g','unit']
    reorder_level: Decimal=Field(ge=0,le=100000,decimal_places=3)
    is_active: bool=True

class MovementInput(Model):
    consumable_id: int=Field(gt=0)
    movement_kind: Literal['receipt','waste','adjustment']
    quantity_delta: Decimal=Field(ge=-1000000,le=1000000,decimal_places=3)
    reason: str=Field(min_length=1,max_length=2000)
    request_key: str=Field(min_length=8,max_length=80)

class RecipeInput(Model):
    consumptions: list[UseInput]=Field(default_factory=list,max_length=30)

class AccountStatusInput(Model):
    is_active: bool

class PasswordResetInput(Model):
    password: str=Field(min_length=8,max_length=128)
