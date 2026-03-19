"""
Seed script for GL Code Classification Tool.

Creates all tables and populates reference data (GL codes, vendors,
vendor services, classification rules) and ingests transaction CSVs.

Usage:
    python -m backend.seed
"""

import csv
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import inspect

from backend.database import engine, SessionLocal, Base
from backend.models import (
    User, GLCode, Vendor, VendorService, ClassificationRule, Transaction,
)


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

GL_CODES = [
    # Level 1
    (4000, "Revenue", 1, "All revenue accounts"),
    (5000, "Cost of Sales", 1, "Direct costs associated with revenue generation"),
    (6000, "Operating Expenses", 1, "General and administrative operating expenses"),
    # Level 2
    (4001, "Premium & Commission Revenue", 2, "Insurance premium revenue and commission income"),
    (4002, "Other Revenue", 2, "Interest income and other non-operating revenue"),
    (5001, "Sales & Marketing", 2, "Direct sales and marketing costs"),
    (5002, "Professional Services", 2, "Consulting and contracted professional services"),
    (6001, "Personnel & Benefits", 2, "Payroll, taxes, and employee benefits"),
    (6002, "Professional Services", 2, "Accounting, legal, and outside services"),
    (6003, "Licensing & Compliance", 2, "Licenses, permits, dues, and subscriptions"),
    (6004, "Office & Operations", 2, "Office supplies, postage, and operational expenses"),
    (6005, "Travel & Entertainment", 2, "Meals, travel, and entertainment expenses"),
    (6006, "Technology", 2, "Computer, internet, and software expenses"),
    (6007, "Insurance", 2, "Business insurance policies"),
    (6008, "Facilities", 2, "Rent, telephone, and utilities"),
    # Level 3
    (4010, "Commission Income", 3, "Insurance commission revenue from carriers"),
    (4030, "Interest Income", 3, "Interest from bank accounts and credit union deposits"),
    (4050, "Other Income", 3, "Tax refunds and miscellaneous income"),
    (5030, "Marketing & Advertising", 3, "Google Ads, Mailchimp campaigns, Klaviyo, marketing events, lead generation services"),
    (5035, "Travel Meals Entertainment - Sales", 3, "Client meals, sales travel, and entertainment for business development"),
    (5100, "Consulting Services", 3, "External consulting engagements"),
    (5215, "Telemarketing", 3, "Outbound calling and lead qualification services"),
    (6020, "Payroll Taxes", 3, "Employer payroll tax obligations"),
    (6030, "Payroll Processing", 3, "Payroll processing fees (Gusto)"),
    (6040, "401K Administration", 3, "Betterment 401K plan administration fees"),
    (6100, "Accounting", 3, "Accounting services (Shelton & Associates, Ricono)"),
    (6110, "Legal", 3, "Legal services (Slotkin Law)"),
    (6115, "Outside Services", 3, "IT support, cleaning, HR services, web development, testing, and other contracted services"),
    (6120, "Licenses & Permits", 3, "State insurance licenses, agent registrations, CE testing, city business licenses"),
    (6130, "Dues & Subscriptions", 3, "Professional memberships, Google One/Apps, LinkedIn Premium, industry associations"),
    (6140, "Postage", 3, "USPS, FedEx, Stamps.com shipping and mailing costs"),
    (6160, "Office Supplies & Expenses", 3, "Office supplies, equipment, groceries for office, Amazon orders, printing"),
    (6170, "Travel Meals Entertainment - Admin", 3, "Employee meals, DoorDash, restaurants, travel, hotels, car rental, team events"),
    (6180, "Education & Training", 3, "Conferences, courses, professional development"),
    (6200, "Computer Internet & Software", 3, "Software subscriptions, internet service"),
    (6210, "Insurance Expense", 3, "Business insurance premiums"),
    (6240, "Rent", 3, "Office rent and lease payments"),
    (6250, "Telephone", 3, "AT&T Fiber, Ring Central phone service"),
    (6260, "Utilities", 3, "Electric, cable/TV"),
]

VENDORS = [
    ("GOOGL", "Google", "active"),
    ("MAILCH", "Mailchimp", "active"),
    ("INSXDT", "InsuranceXDate", "active"),
    ("BETTRM", "Betterment", "active"),
    ("RICONO", "Ricono Accounting", "active"),
    ("ASCEND", "Ascend Payments", "active"),
    ("ATLOFF", "Atlanta Office Technology", "active"),
    ("MDTECH", "MedTech Consultants", "active"),
    ("INDEED", "Indeed", "active"),
    ("VSP", "VSP", "active"),
    ("IDEMIA", "IDEMIA", "active"),
    ("BRADY", "Brady Pest Control", "active"),
    ("DOMAIN", "Domain.com", "active"),
    ("SIRCON", "Vertafore Sircon", "active"),
    ("MONedu", "MonitorEDU", "active"),
    ("VUE", "Pearson VUE", "active"),
    ("GABPMS", "Georgia Baptist Mission", "active"),
    ("PROFIN", "Professional Insurance Agents", "active"),
    ("USPS", "USPS", "active"),
    ("WALMRT", "Walmart", "active"),
    ("AMAZON", "Amazon", "active"),
    ("KUDOBD", "Kudoboard", "active"),
    ("HOBBY", "Hobby Lobby", "active"),
    ("POPSHL", "PopShelf", "active"),
    ("DLRTEE", "Dollar Tree", "active"),
    ("KROGER", "Kroger", "active"),
    ("WALGRN", "Walgreens", "active"),
    ("VSTAPR", "VistaPrint", "active"),
    ("DRDSH", "DoorDash", "active"),
    ("HUEYMS", "Huey Magoos", "active"),
    ("BRCOFF", "Black Rifle Coffee", "active"),
    ("CHKFLA", "Chick-fil-A", "active"),
    ("GRTHVT", "Great Harvest Bread", "active"),
    ("ATHGYR", "Athena's Gyros", "active"),
    ("RRTACO", "RReal Tacos", "active"),
    ("CITYBB", "City BBQ", "active"),
    ("SUKI", "Suki", "active"),
    ("CHILIS", "Chili's", "active"),
    ("DOMINO", "Domino's", "active"),
    ("GRAYSC", "Grayson Sweet Home Cafe", "active"),
    ("MRTACO", "Mr. Taco", "active"),
    ("ELRNCH", "El Ranchero", "active"),
    ("AMPROF", "America's Professor", "active"),
    ("MSFT", "Microsoft", "active"),
    ("CANOPY", "Canopy (UseCanopy)", "active"),
    ("OPENAI", "OpenAI", "active"),
    ("APEX", "Apex Software", "active"),
    ("ADOBE", "Adobe", "active"),
    ("DOCSIG", "DocuSign", "active"),
    ("ATT", "AT&T", "active"),
    ("COMCST", "Comcast", "active"),
    ("WALTEM", "Walton EMC", "active"),
    ("HERTZ", "Hertz", "active"),
    ("HAMPTN", "Hampton Inn", "active"),
    ("HILTON", "Hilton", "active"),
    ("EXXON", "ExxonMobil", "active"),
    ("ORBITZ", "Orbitz", "active"),
    ("TAILWD", "Tailwind", "active"),
    ("ATLBRV", "Atlanta Braves", "active"),
    ("RSCANE", "Raising Cane's", "active"),
    ("DTCHBR", "Dutch Bros", "active"),
    ("CHECKR", "Checkr", "active"),
    ("KLAVYO", "Klaviyo", "active"),
    ("CAMPBL", "Campbell Group", "active"),
    ("FIGLEF", "Fig Leaf Advisor", "active"),
    ("BRHALL", "Brandon Hall", "active"),
    ("OOFAKD", "One Of A Kind", "active"),
    ("GUSTO", "Gusto", "active"),
    ("SHELTN", "Shelton & Associates", "active"),
    ("SLTKLN", "Slotkin Law", "active"),
    ("ALICOR", "Alicor", "active"),
    ("HUMINT", "Human Interest", "active"),
    ("JUANA", "Juana Alfaro", "active"),
    ("RECOAT", "Reco Atlanta Glass", "active"),
    ("TALOGY", "Talogy Caliper", "active"),
    ("TOTCSR", "Total CSR", "active"),
    ("CITYOL", "City of Loganville", "active"),
    ("NIPR", "NIPR", "active"),
    ("CLB", "CLB GA Insurance", "active"),
    ("LINKDN", "LinkedIn", "active"),
    ("FEDEX", "FedEx", "active"),
    ("STAMPS", "Stamps.com", "active"),
    ("ALDI", "Aldi", "active"),
    ("HOMEDP", "Home Depot", "active"),
    ("LOWES", "Lowe's", "active"),
    ("MARLIN", "Marlin Copier", "active"),
    ("OFFDPT", "Office Depot", "active"),
    ("OFFMAX", "Office Max", "active"),
    ("PERCON", "Personnel Concepts", "active"),
    ("PUBLIX", "Publix", "active"),
    ("QUILL", "Quill", "active"),
    ("SAMSCLB", "Sam's Club", "active"),
    ("TJMAX", "TJ Maxx", "active"),
    ("UHAUL", "U-Haul", "active"),
    ("ZOOM", "Zoom", "active"),
    ("RINGCN", "Ring Central", "active"),
    ("FLASHE", "Flash Electric", "active"),
    ("UTICA", "Utica National", "active"),
    ("PRNCPL", "Principal Life", "active"),
    ("PROTLF", "Protective Life", "active"),
    ("PPLKEP", "PeopleKeep", "active"),
    ("HRTFRD", "The Hartford", "active"),
    ("ZAXBYS", "Zaxby's", "active"),
    ("MARITZ", "Maritz Global", "active"),
    ("DELTCU", "Delta Community CU", "active"),
    ("IRS", "Internal Revenue Service", "active"),
    ("APPLDS", "Applied Systems", "active"),
]

VENDOR_SERVICES = [
    ("GOOGL-ADS", "GOOGL", "Google Ads", "active"),
    ("GOOGL-ONE", "GOOGL", "Google One", "active"),
    ("GOOGL-APPS", "GOOGL", "Google Apps/Workspace", "active"),
    ("COMCST-INT", "COMCST", "Comcast Internet", "active"),
    ("COMCST-CBL", "COMCST", "Comcast Cable/TV", "active"),
    ("DRDSH-CUBBY", "DRDSH", "Cubby's", "active"),
    ("DRDSH-MCDNL", "DRDSH", "McDonald's", "active"),
    ("DRDSH-CHPTL", "DRDSH", "Chipotle", "active"),
    ("DRDSH-BNDBU", "DRDSH", "Bandana Burgers", "active"),
    ("DRDSH-CHKFL", "DRDSH", "Chick-fil-A", "active"),
    ("DRDSH-CHILI", "DRDSH", "Chili's", "active"),
    ("DRDSH-LOSRB", "DRDSH", "Los Aribenos", "active"),
    ("DRDSH-MIGEL", "DRDSH", "Miguel's", "active"),
    ("DRDSH-SMOKE", "DRDSH", "The Smokey Pig", "active"),
    ("MSFT-365", "MSFT", "Microsoft 365", "active"),
    ("MSFT-AZURE", "MSFT", "Microsoft Azure", "active"),
    ("VSP-WRKWSE", "VSP", "VSP Workwise Compliance", "active"),
    ("AMAZON-PRM", "AMAZON", "Amazon Prime", "active"),
    ("AMAZON-MKT", "AMAZON", "Amazon Marketplace", "active"),
    ("MAILCH-MKTG", "MAILCH", "Mailchimp Marketing Platform", "active"),
    ("OPENAI-CGPT", "OPENAI", "ChatGPT Subscription", "active"),
    ("ADOBE-PRO", "ADOBE", "Adobe Creative Suite", "active"),
    ("FIGLEF-CONS", "FIGLEF", "Consulting Services", "active"),
    ("FIGLEF-RENT", "FIGLEF", "Office Rent", "active"),
    ("ATT-FIBER", "ATT", "AT&T Fiber/Uverse", "active"),
    ("WALTEM-ELEC", "WALTEM", "Electric Service", "active"),
]

# (vendor_id, service_id, amount_min, amount_max, tom_start, tom_end, gl_code, is_active)
CLASSIFICATION_RULES = [
    # 5030 Marketing & Advertising
    ("GOOGL", "GOOGL-ADS", None, None, None, None, 5030, True),
    ("INSXDT", None, None, None, None, None, 5030, True),
    ("KLAVYO", None, None, None, None, None, 5030, True),
    ("MARITZ", None, None, None, None, None, 5030, True),
    # 5100 Consulting Services
    ("CAMPBL", None, None, None, None, None, 5100, True),
    ("FIGLEF", "FIGLEF-CONS", None, None, None, None, 5100, True),
    ("BRHALL", None, None, None, None, None, 5100, True),
    # 5215 Telemarketing
    ("OOFAKD", None, None, None, None, None, 5215, True),
    # 6020 Payroll Taxes
    ("GUSTO", None, None, None, None, None, 6020, True),
    # 6040 401K
    ("BETTRM", None, None, None, None, None, 6040, True),
    # 6100 Accounting
    ("SHELTN", None, None, None, None, None, 6100, True),
    ("RICONO", None, None, None, None, None, 6100, True),
    # 6110 Legal
    ("SLTKLN", None, None, None, None, None, 6110, True),
    # 6115 Outside Services
    ("ALICOR", None, None, None, None, None, 6115, True),
    ("ASCEND", None, None, None, None, None, 6115, True),
    ("ATLOFF", None, None, None, None, None, 6115, True),
    ("HUMINT", None, None, None, None, None, 6115, True),
    ("INDEED", None, None, None, None, None, 6115, True),
    ("JUANA", None, None, None, None, None, 6115, True),
    ("MDTECH", None, None, None, None, None, 6115, True),
    ("RECOAT", None, None, None, None, None, 6115, True),
    ("TALOGY", None, None, None, None, None, 6115, True),
    ("TOTCSR", None, None, None, None, None, 6115, True),
    ("VSP", "VSP-WRKWSE", None, None, None, None, 6115, True),
    ("IDEMIA", None, None, None, None, None, 6115, True),
    ("BRADY", None, None, None, None, None, 6115, True),
    ("DOMAIN", None, None, None, None, None, 6115, True),
    # 6120 Licenses & Permits
    ("SIRCON", None, None, None, None, None, 6120, True),
    ("CITYOL", None, None, None, None, None, 6120, True),
    ("NIPR", None, None, None, None, None, 6120, True),
    ("CLB", None, None, None, None, None, 6120, True),
    ("MONedu", None, None, None, None, None, 6120, True),
    ("VUE", None, None, None, None, None, 6120, True),
    # 6130 Dues & Subscriptions
    ("LINKDN", None, None, None, None, None, 6130, True),
    ("GOOGL", "GOOGL-ONE", None, None, None, None, 6130, True),
    ("GOOGL", "GOOGL-APPS", None, None, None, None, 6130, True),
    ("GABPMS", None, None, None, None, None, 6130, True),
    ("PROFIN", None, None, None, None, None, 6130, True),
    # 6140 Postage
    ("USPS", None, None, None, None, None, 6140, True),
    ("FEDEX", None, None, None, None, None, 6140, True),
    ("STAMPS", None, None, None, None, None, 6140, True),
    # 6160 Office Supplies
    ("WALMRT", None, None, None, None, None, 6160, True),
    ("AMAZON", None, None, None, None, None, 6160, True),
    ("HOBBY", None, None, None, None, None, 6160, True),
    ("HOMEDP", None, None, None, None, None, 6160, True),
    ("KROGER", None, None, None, None, None, 6160, True),
    ("LOWES", None, None, None, None, None, 6160, True),
    ("MARLIN", None, None, None, None, None, 6160, True),
    ("OFFDPT", None, None, None, None, None, 6160, True),
    ("OFFMAX", None, None, None, None, None, 6160, True),
    ("PERCON", None, None, None, None, None, 6160, True),
    ("PUBLIX", None, None, None, None, None, 6160, True),
    ("QUILL", None, None, None, None, None, 6160, True),
    ("SAMSCLB", None, None, None, None, None, 6160, True),
    ("TJMAX", None, None, None, None, None, 6160, True),
    ("UHAUL", None, None, None, None, None, 6160, True),
    ("VSTAPR", None, None, None, None, None, 6160, True),
    ("ALDI", None, None, None, None, None, 6160, True),
    ("KUDOBD", None, None, None, None, None, 6160, True),
    ("POPSHL", None, None, None, None, None, 6160, True),
    ("DLRTEE", None, None, None, None, None, 6160, True),
    ("WALGRN", None, None, None, None, None, 6160, True),
    # 6170 Travel Meals Entertainment - Admin
    ("DRDSH", None, None, None, None, None, 6170, True),
    ("HUEYMS", None, None, None, None, None, 6170, True),
    ("BRCOFF", None, None, None, None, None, 6170, True),
    ("CHKFLA", None, None, None, None, None, 6170, True),
    ("GRTHVT", None, None, None, None, None, 6170, True),
    ("ATHGYR", None, None, None, None, None, 6170, True),
    ("RRTACO", None, None, None, None, None, 6170, True),
    ("CITYBB", None, None, None, None, None, 6170, True),
    ("SUKI", None, None, None, None, None, 6170, True),
    ("CHILIS", None, None, None, None, None, 6170, True),
    ("DOMINO", None, None, None, None, None, 6170, True),
    ("GRAYSC", None, None, None, None, None, 6170, True),
    ("MRTACO", None, None, None, None, None, 6170, True),
    ("ELRNCH", None, None, None, None, None, 6170, True),
    ("ZAXBYS", None, None, None, None, None, 6170, True),
    ("RSCANE", None, None, None, None, None, 6170, True),
    ("DTCHBR", None, None, None, None, None, 6170, True),
    ("HERTZ", None, None, None, None, None, 6170, True),
    ("HAMPTN", None, None, None, None, None, 6170, True),
    ("HILTON", None, None, None, None, None, 6170, True),
    ("EXXON", None, None, None, None, None, 6170, True),
    ("ORBITZ", None, None, None, None, None, 6170, True),
    ("TAILWD", None, None, None, None, None, 6170, True),
    ("ATLBRV", None, None, None, None, None, 6170, True),
    # 6180 Education & Training
    ("AMPROF", None, None, None, None, None, 6180, True),
    # 6200 Computer Internet & Software
    ("MSFT", None, None, None, None, None, 6200, True),
    ("CANOPY", None, None, None, None, None, 6200, True),
    ("OPENAI", None, None, None, None, None, 6200, True),
    ("APEX", None, None, None, None, None, 6200, True),
    ("ADOBE", None, None, None, None, None, 6200, True),
    ("DOCSIG", None, None, None, None, None, 6200, True),
    ("ZOOM", None, None, None, None, None, 6200, True),
    ("APPLDS", None, None, None, None, None, 6200, True),
    ("COMCST", "COMCST-INT", None, None, None, None, 6200, True),
    # 6210 Insurance
    ("UTICA", None, None, None, None, None, 6210, True),
    ("PRNCPL", None, None, None, None, None, 6210, True),
    ("PROTLF", None, None, None, None, None, 6210, True),
    ("PPLKEP", None, None, None, None, None, 6210, True),
    ("HRTFRD", None, None, None, None, None, 6210, True),
    # 6240 Rent
    ("FIGLEF", "FIGLEF-RENT", None, None, None, None, 6240, True),
    # 6250 Telephone
    ("ATT", None, None, None, None, None, 6250, True),
    ("RINGCN", None, None, None, None, None, 6250, True),
    # 6260 Utilities
    ("COMCST", "COMCST-CBL", None, None, None, None, 6260, True),
    ("WALTEM", None, None, None, None, None, 6260, True),
    ("FLASHE", None, None, None, None, None, 6260, True),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_amount(raw: str) -> Decimal | None:
    """Parse amount strings like '$519.94', '($860.30)', '$1,234.56'."""
    if not raw:
        return None
    s = raw.strip()
    negative = False
    # Handle parenthetical negatives: ($X.XX) -> -X.XX
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    # Strip dollar sign and commas
    s = s.replace("$", "").replace(",", "").strip()
    if not s:
        return None
    try:
        val = Decimal(s)
    except InvalidOperation:
        return None
    return -val if negative else val


def parse_date(raw: str) -> datetime | None:
    """Parse M/D/YYYY date strings."""
    if not raw or not raw.strip():
        return None
    try:
        return datetime.strptime(raw.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def resolve_csv_path(docker_path: str, local_relative: str) -> str:
    """Return the CSV path, preferring Docker path if it exists."""
    if os.path.exists(docker_path):
        return docker_path
    # Resolve local path relative to project root (parent of backend/)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_path = os.path.join(project_root, local_relative)
    return local_path


# ---------------------------------------------------------------------------
# Seeding functions
# ---------------------------------------------------------------------------

def seed_user(session):
    """Seed demo user."""
    existing = session.query(User).filter_by(username="demo_user").first()
    if existing:
        print("  Demo user already exists, skipping.")
        return existing
    user = User(username="demo_user", role="read_write")
    session.add(user)
    session.flush()
    print("  Created demo user.")
    return user


def seed_gl_codes(session):
    """Seed GL code hierarchy."""
    existing_count = session.query(GLCode).count()
    if existing_count >= len(GL_CODES):
        print(f"  GL codes already seeded ({existing_count} rows), skipping.")
        return
    for code, gl_class, level, description in GL_CODES:
        existing = session.query(GLCode).filter_by(gl_code=code).first()
        if existing:
            continue
        session.add(GLCode(
            gl_code=code,
            gl_class=gl_class,
            gl_level=level,
            description=description,
        ))
    session.flush()
    print(f"  Seeded {len(GL_CODES)} GL codes.")


def seed_vendors(session):
    """Seed vendors."""
    existing_count = session.query(Vendor).count()
    if existing_count >= len(VENDORS):
        print(f"  Vendors already seeded ({existing_count} rows), skipping.")
        return
    for vendor_id, vendor_name, status in VENDORS:
        existing = session.query(Vendor).filter_by(vendor_id=vendor_id).first()
        if existing:
            continue
        session.add(Vendor(
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            status=status,
        ))
    session.flush()
    print(f"  Seeded {len(VENDORS)} vendors.")


def seed_vendor_services(session):
    """Seed vendor services."""
    existing_count = session.query(VendorService).count()
    if existing_count >= len(VENDOR_SERVICES):
        print(f"  Vendor services already seeded ({existing_count} rows), skipping.")
        return
    for service_id, vendor_id, service_name, status in VENDOR_SERVICES:
        existing = session.query(VendorService).filter_by(service_id=service_id).first()
        if existing:
            continue
        session.add(VendorService(
            service_id=service_id,
            vendor_id=vendor_id,
            service_name=service_name,
            status=status,
        ))
    session.flush()
    print(f"  Seeded {len(VENDOR_SERVICES)} vendor services.")


def seed_classification_rules(session):
    """Seed classification rules."""
    existing_count = session.query(ClassificationRule).count()
    if existing_count >= len(CLASSIFICATION_RULES):
        print(f"  Classification rules already seeded ({existing_count} rows), skipping.")
        return
    for vendor_id, service_id, amt_min, amt_max, tom_start, tom_end, gl_code, is_active in CLASSIFICATION_RULES:
        # Check for duplicate by unique combination
        q = session.query(ClassificationRule).filter_by(
            vendor_id=vendor_id,
            gl_code=gl_code,
        )
        if service_id is not None:
            q = q.filter_by(service_id=service_id)
        else:
            q = q.filter(ClassificationRule.service_id.is_(None))
        if q.first():
            continue
        session.add(ClassificationRule(
            vendor_id=vendor_id,
            service_id=service_id,
            amount_min=amt_min,
            amount_max=amt_max,
            time_of_month_start=tom_start,
            time_of_month_end=tom_end,
            gl_code=gl_code,
            is_active=is_active,
        ))
    session.flush()
    print(f"  Seeded {len(CLASSIFICATION_RULES)} classification rules.")


def ingest_classified_csv(session):
    """Ingest classified.csv - pre-classified transactions."""
    csv_path = resolve_csv_path("/app/data/classified.csv", "data/classified.csv")
    if not os.path.exists(csv_path):
        print(f"  WARNING: classified.csv not found at {csv_path}, skipping.")
        return

    # Check if already ingested
    existing = session.query(Transaction).filter(
        Transaction.transaction_id.like("CLF-%")
    ).count()
    if existing > 0:
        print(f"  classified.csv already ingested ({existing} rows), skipping.")
        return

    row_num = 0
    ingested = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # skip header
        for row in reader:
            row_num += 1
            # Strip trailing empty columns
            while row and not row[-1].strip():
                row.pop()
            if len(row) < 4:
                continue

            date_str = row[0].strip()
            description = row[1].strip()
            amount_str = row[2].strip()
            gl_code_str = row[3].strip()

            # Skip rows with empty dates or descriptions
            date_val = parse_date(date_str)
            if date_val is None or not description:
                continue

            amount_val = parse_amount(amount_str)
            if amount_val is None:
                continue

            # Parse GL code
            try:
                gl_code = int(gl_code_str)
            except (ValueError, TypeError):
                gl_code = None

            txn_id = f"CLF-{row_num:03d}"

            session.add(Transaction(
                transaction_id=txn_id,
                version=1,
                date=date_val,
                raw_description=description,
                amount=amount_val,
                gl_code=gl_code,
                confidence="High",
                method="Rule Match",
                review_status="Approved",
                source_file="classified.csv",
            ))
            ingested += 1

    session.flush()
    print(f"  Ingested {ingested} transactions from classified.csv.")


def ingest_classify_csv(session):
    """Ingest classify.csv - transactions to be classified."""
    csv_path = resolve_csv_path("/app/data/classify.csv", "data/classify.csv")
    if not os.path.exists(csv_path):
        print(f"  WARNING: classify.csv not found at {csv_path}, skipping.")
        return

    # Check if already ingested
    existing = session.query(Transaction).filter(
        Transaction.transaction_id.like("NEW-%")
    ).count()
    if existing > 0:
        print(f"  classify.csv already ingested ({existing} rows), skipping.")
        return

    row_num = 0
    ingested = 0
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)  # skip header
        for row in reader:
            row_num += 1
            if len(row) < 3:
                continue

            date_str = row[0].strip()
            description = row[1].strip()
            amount_str = row[2].strip()

            # Skip rows with empty dates or descriptions
            date_val = parse_date(date_str)
            if date_val is None or not description:
                continue

            amount_val = parse_amount(amount_str)
            if amount_val is None:
                continue

            txn_id = f"NEW-{row_num:03d}"

            session.add(Transaction(
                transaction_id=txn_id,
                version=1,
                date=date_val,
                raw_description=description,
                amount=amount_val,
                review_status="Unreviewed",
                source_file="classify.csv",
            ))
            ingested += 1

    session.flush()
    print(f"  Ingested {ingested} transactions from classify.csv.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def seed():
    """Run all seed operations."""
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created.\n")

    session = SessionLocal()
    try:
        print("Seeding reference data...")
        seed_user(session)
        seed_gl_codes(session)
        seed_vendors(session)
        seed_vendor_services(session)
        seed_classification_rules(session)
        print()

        # CSV ingestion removed — transactions are now uploaded via the UI
        # drag-and-drop feature instead of being seeded from the backend.
        print("Skipping CSV ingestion (use UI drag-and-drop to upload).")

        session.commit()
        print("Seed completed successfully.")
    except Exception as e:
        session.rollback()
        print(f"ERROR during seeding: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
