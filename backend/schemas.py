from pydantic import BaseModel
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Any


# --- GL Codes ---
class GLCodeOut(BaseModel):
    gl_code: int
    gl_class: str
    gl_level: int
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class GLCodeHierarchy(BaseModel):
    gl_code: int
    gl_class: str
    gl_level: int
    description: Optional[str] = None
    children: list["GLCodeHierarchy"] = []


# --- Vendors ---
class VendorServiceOut(BaseModel):
    service_id: str
    vendor_id: str
    service_name: str
    status: str

    model_config = {"from_attributes": True}


class VendorOut(BaseModel):
    vendor_id: str
    vendor_name: str
    status: str
    created_at: Optional[datetime] = None
    services: list[VendorServiceOut] = []
    transaction_count: int = 0

    model_config = {"from_attributes": True}


class VendorCreate(BaseModel):
    vendor_id: str
    vendor_name: str
    user_id: Optional[int] = None


class VendorServiceCreate(BaseModel):
    service_id: str
    service_name: str
    user_id: Optional[int] = None


class VendorConfirm(BaseModel):
    user_id: int


# --- Classification Rules ---
class RuleOut(BaseModel):
    rule_id: int
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    service_id: Optional[str] = None
    service_name: Optional[str] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    time_of_month_start: Optional[int] = None
    time_of_month_end: Optional[int] = None
    gl_code: int
    gl_class: Optional[str] = None
    reasoning: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None
    match_count: int = 0

    model_config = {"from_attributes": True}


class RuleCreate(BaseModel):
    vendor_id: Optional[str] = None
    service_id: Optional[str] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    time_of_month_start: Optional[int] = None
    time_of_month_end: Optional[int] = None
    gl_code: int
    reasoning: Optional[str] = None
    user_id: Optional[int] = None


class RuleUpdate(BaseModel):
    vendor_id: Optional[str] = None
    service_id: Optional[str] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    time_of_month_start: Optional[int] = None
    time_of_month_end: Optional[int] = None
    gl_code: Optional[int] = None
    is_active: Optional[bool] = None


# --- Transactions ---
class TransactionOut(BaseModel):
    id: int
    transaction_id: str
    version: int
    date: date
    raw_description: str
    amount: Decimal
    vendor_id: Optional[str] = None
    service_id: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    is_expense: bool
    gl_code: Optional[int] = None
    gl_class: Optional[str] = None
    confidence: Optional[str] = None
    method: Optional[str] = None
    rule_id: Optional[int] = None
    reasoning: Optional[str] = None
    review_status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    source_file: Optional[str] = None
    upload_batch: Optional[str] = None
    created_at: Optional[datetime] = None
    vendor_name: Optional[str] = None

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    transactions: list[TransactionOut]
    total: int
    page: int
    page_size: int


class TransactionApprove(BaseModel):
    user_id: int


class TransactionReclassify(BaseModel):
    gl_code: int
    user_id: int
    notes: Optional[str] = None


class TransactionFlag(BaseModel):
    user_id: int
    notes: Optional[str] = None


class ConvertToRule(BaseModel):
    vendor_id: Optional[str] = None
    service_id: Optional[str] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    time_of_month_start: Optional[int] = None
    time_of_month_end: Optional[int] = None
    gl_code: int
    user_id: Optional[int] = None


# --- Classification ---
class ClassifyRequest(BaseModel):
    source_file: Optional[str] = None


class ClassifyResponse(BaseModel):
    total: int
    pre_classified: int = 0
    classified_by_rule: int
    medium_confidence: int
    unclassified: int
    non_expense: int


class UploadResponse(BaseModel):
    filename: str
    transactions_ingested: int
    transactions_skipped: int
    source_file: str
    upload_batch: str


# --- Rule Suggestions ---
class RuleSuggestion(BaseModel):
    vendor_id: str
    vendor_name: str
    service_id: Optional[str] = None
    service_name: Optional[str] = None
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    gl_code: int
    gl_class: Optional[str] = None
    reasoning: str
    affected_transaction_ids: list[str] = []
    affected_count: int = 0


class SuggestRulesResponse(BaseModel):
    suggestions: list[RuleSuggestion]
    total_unclassified: int


class AcceptSuggestionsRequest(BaseModel):
    suggestions: list[dict[str, Any]]
    user_id: int = 1


class ReclassifyResponse(BaseModel):
    total_reclassified: int
    newly_classified: int
    still_unclassified: int


# --- Stats ---
class StatsResponse(BaseModel):
    total_transactions: int
    by_review_status: dict[str, int]
    by_confidence: dict[str, int]
    by_method: dict[str, int]
    by_gl_code: dict[str, int]
