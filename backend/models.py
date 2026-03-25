from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Numeric, Date, DateTime,
    ForeignKey, Index, CheckConstraint, UniqueConstraint, func
)
from sqlalchemy.orm import relationship
from backend.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('read_only', 'read_write')", name="ck_users_role"),
    )


class GLCode(Base):
    __tablename__ = "gl_codes"

    gl_code = Column(Integer, primary_key=True)
    gl_class = Column(String(255), nullable=False)
    gl_level = Column(Integer, nullable=False)
    description = Column(Text)


class Vendor(Base):
    __tablename__ = "vendors"

    vendor_id = Column(String(20), primary_key=True)
    vendor_name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, server_default="pending_confirmation")
    created_by = Column(Integer, ForeignKey("users.user_id"))
    confirmed_by = Column(Integer, ForeignKey("users.user_id"))
    confirmed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    services = relationship("VendorService", back_populates="vendor")

    __table_args__ = (
        CheckConstraint("status IN ('active', 'pending_confirmation')", name="ck_vendors_status"),
    )


class VendorService(Base):
    __tablename__ = "vendor_services"

    service_id = Column(String(30), primary_key=True)
    vendor_id = Column(String(20), ForeignKey("vendors.vendor_id"), nullable=False)
    service_name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, server_default="pending_confirmation")
    created_by = Column(Integer, ForeignKey("users.user_id"))
    confirmed_by = Column(Integer, ForeignKey("users.user_id"))
    confirmed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

    vendor = relationship("Vendor", back_populates="services")

    __table_args__ = (
        UniqueConstraint("vendor_id", "service_name", name="uq_vendor_service"),
        CheckConstraint("status IN ('active', 'pending_confirmation')", name="ck_vendor_services_status"),
    )


class DescriptionVendorMap(Base):
    __tablename__ = "description_vendor_map"

    map_id = Column(Integer, primary_key=True, autoincrement=True)
    description_pattern = Column(String(255), nullable=False, unique=True)
    vendor_id = Column(String(20), ForeignKey("vendors.vendor_id"), nullable=False)
    service_id = Column(String(30), ForeignKey("vendor_services.service_id"))
    city = Column(String(100))
    state = Column(String(50))
    country = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_desc_vendor_map_pattern", "description_pattern"),
    )


class ClassificationRule(Base):
    __tablename__ = "classification_rules"

    rule_id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id = Column(String(20), ForeignKey("vendors.vendor_id"))
    service_id = Column(String(30), ForeignKey("vendor_services.service_id"))
    amount_min = Column(Numeric(12, 2))
    amount_max = Column(Numeric(12, 2))
    time_of_month_start = Column(Integer)
    time_of_month_end = Column(Integer)
    gl_code = Column(Integer, ForeignKey("gl_codes.gl_code"), nullable=False)
    reasoning = Column(Text)
    is_active = Column(Boolean, server_default="true")
    created_by = Column(Integer, ForeignKey("users.user_id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "time_of_month_start IS NULL OR (time_of_month_start BETWEEN 1 AND 31)",
            name="ck_rules_tom_start",
        ),
        CheckConstraint(
            "time_of_month_end IS NULL OR (time_of_month_end BETWEEN 1 AND 31)",
            name="ck_rules_tom_end",
        ),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(50), nullable=False)
    version = Column(Integer, nullable=False, server_default="1")
    date = Column(Date, nullable=False)
    raw_description = Column(Text, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    vendor_id = Column(String(20), ForeignKey("vendors.vendor_id"))
    service_id = Column(String(30), ForeignKey("vendor_services.service_id"))
    city = Column(String(100))
    state = Column(String(50))
    country = Column(String(100))
    is_expense = Column(Boolean, server_default="true")
    gl_code = Column(Integer, ForeignKey("gl_codes.gl_code"))
    confidence = Column(String(10))
    method = Column(String(20))
    rule_id = Column(Integer, ForeignKey("classification_rules.rule_id"))
    reasoning = Column(Text)
    review_status = Column(String(20), server_default="Unreviewed")
    reviewed_by = Column(Integer, ForeignKey("users.user_id"))
    reviewed_at = Column(DateTime)
    source_file = Column(String(255))
    upload_batch = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("transaction_id", "version", name="uq_txn_version"),
        Index("idx_transactions_current", "transaction_id", version.desc()),
        CheckConstraint(
            "confidence IS NULL OR confidence IN ('High', 'Medium', 'Low')",
            name="ck_txn_confidence",
        ),
        CheckConstraint(
            "method IS NULL OR method IN ('Rule Match', 'LLM Inference', 'Unclassifiable', 'Unclassified', 'Pre-classified', 'Manual')",
            name="ck_txn_method",
        ),
        CheckConstraint(
            "review_status IN ('Unreviewed', 'Approved', 'Reclassified', 'Flagged')",
            name="ck_txn_review_status",
        ),
    )
