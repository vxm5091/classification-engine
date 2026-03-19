# GL Code Classification Tool — Implementation Plan

## Overview

Build a full-stack prototype: React frontend → FastAPI backend → PostgreSQL database. The tool classifies financial transactions into GL codes using a two-layer Classification Engine (deterministic rules + LLM inference), with a review workflow for accountants.

**Reference the attached CSV files for data ingestion:**
- `classified.csv` — Historical transactions with assigned GL codes (290 rows)
- `classify.csv` — New transactions needing classification (290 rows)
- `gl_code_dictionary.csv` — Vendor-to-GL-code reference (119 rows)

---

## Tech Stack

- **Frontend:** React (Vite), TailwindCSS, React Query for API state management
- **Backend:** Python, FastAPI, SQLAlchemy ORM, Pydantic for request/response models
- **Database:** PostgreSQL
- **LLM:** Anthropic Claude API (claude-sonnet-4-20250514) for vendor resolution and GL classification inference
- **Containerization:** Docker Compose for local development (PostgreSQL + FastAPI + React)

---

## 1. Database Schema (PostgreSQL)

### 1.1 Users

```sql
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('read_only', 'read_write')),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 1.2 GL Codes

```sql
CREATE TABLE gl_codes (
    gl_code INT PRIMARY KEY,
    gl_class VARCHAR(255) NOT NULL,
    gl_level INT NOT NULL,
    description TEXT
);
```

**Preload data — GL Hierarchy:**

All revenue and expense accounts are at level 3. Level 1 and 2 are structural groupings for the hierarchy reference view.

```sql
-- Level 1: Financial Statement Categories
INSERT INTO gl_codes (gl_code, gl_class, gl_level, description) VALUES
(4000, 'Revenue', 1, 'All revenue accounts'),
(5000, 'Cost of Sales', 1, 'Direct costs associated with revenue generation'),
(6000, 'Operating Expenses', 1, 'General and administrative operating expenses');

-- Level 2: Subcategories
INSERT INTO gl_codes (gl_code, gl_class, gl_level, description) VALUES
(4001, 'Premium & Commission Revenue', 2, 'Insurance premium revenue and commission income'),
(4002, 'Other Revenue', 2, 'Interest income and other non-operating revenue'),
(5001, 'Sales & Marketing', 2, 'Direct sales and marketing costs'),
(5002, 'Professional Services', 2, 'Consulting and contracted professional services'),
(6001, 'Personnel & Benefits', 2, 'Payroll, taxes, and employee benefits'),
(6002, 'Professional Services', 2, 'Accounting, legal, and outside services'),
(6003, 'Licensing & Compliance', 2, 'Licenses, permits, dues, and subscriptions'),
(6004, 'Office & Operations', 2, 'Office supplies, postage, and operational expenses'),
(6005, 'Travel & Entertainment', 2, 'Meals, travel, and entertainment expenses'),
(6006, 'Technology', 2, 'Computer, internet, and software expenses'),
(6007, 'Insurance', 2, 'Business insurance policies (E&O, P&C, life, health, WC)'),
(6008, 'Facilities', 2, 'Rent, telephone, and utilities');

-- Level 3: Operational Accounts (these are the accounts transactions are coded to)
INSERT INTO gl_codes (gl_code, gl_class, gl_level, description) VALUES
-- Revenue
(4010, 'Commission Income', 3, 'Insurance commission revenue from carriers'),
(4030, 'Interest Income', 3, 'Interest from bank accounts and credit union deposits'),
(4050, 'Other Income', 3, 'Tax refunds and miscellaneous income'),
-- Cost of Sales
(5030, 'Marketing & Advertising', 3, 'Google Ads, Mailchimp campaigns, Klaviyo, marketing events, lead generation services'),
(5035, 'Travel Meals Entertainment - Sales', 3, 'Client meals, sales travel, and entertainment for business development'),
(5100, 'Consulting Services', 3, 'External consulting engagements (Campbell Group, Fig Leaf, Brandon Hall)'),
(5215, 'Telemarketing', 3, 'Outbound calling and lead qualification services'),
-- Operating Expenses: Personnel & Benefits
(6020, 'Payroll Taxes', 3, 'Employer payroll tax obligations'),
(6030, 'Payroll Processing', 3, 'Payroll processing fees (Gusto)'),
(6040, '401K Administration', 3, 'Betterment 401K plan administration fees'),
-- Operating Expenses: Professional Services
(6100, 'Accounting', 3, 'Accounting services (Shelton & Associates, Ricono)'),
(6110, 'Legal', 3, 'Legal services (Slotkin Law)'),
(6115, 'Outside Services', 3, 'IT support, cleaning, HR services, web development, testing, and other contracted services'),
-- Operating Expenses: Licensing & Compliance
(6120, 'Licenses & Permits', 3, 'State insurance licenses, agent registrations, CE testing, city business licenses'),
(6130, 'Dues & Subscriptions', 3, 'Professional memberships, Google One/Apps, LinkedIn Premium, industry associations'),
-- Operating Expenses: Office & Operations
(6140, 'Postage', 3, 'USPS, FedEx, Stamps.com shipping and mailing costs'),
(6160, 'Office Supplies & Expenses', 3, 'Office supplies, equipment, groceries for office, Amazon orders, printing'),
-- Operating Expenses: Travel & Entertainment
(6170, 'Travel Meals Entertainment - Admin', 3, 'Employee meals, DoorDash, restaurants, travel, hotels, car rental, team events'),
(6180, 'Education & Training', 3, 'Conferences, courses, professional development'),
-- Operating Expenses: Technology
(6200, 'Computer Internet & Software', 3, 'Software subscriptions (Microsoft, Adobe, OpenAI, Canopy, Zoom), internet service'),
-- Operating Expenses: Insurance
(6210, 'Insurance Expense', 3, 'Business insurance premiums — E&O, property & casualty, workers comp, life, health'),
-- Operating Expenses: Facilities
(6240, 'Rent', 3, 'Office rent and lease payments'),
(6250, 'Telephone', 3, 'AT&T Fiber, Ring Central phone service'),
(6260, 'Utilities', 3, 'Electric (Walton EMC), cable/TV (Comcast Cable)');
```

### 1.3 Vendors

```sql
CREATE TABLE vendors (
    vendor_id VARCHAR(10) PRIMARY KEY CHECK (vendor_id = UPPER(vendor_id)),
    vendor_name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending_confirmation' CHECK (status IN ('active', 'pending_confirmation')),
    created_by INT REFERENCES users(user_id),  -- NULL if system-generated
    confirmed_by INT REFERENCES users(user_id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 1.4 Vendor Services

```sql
CREATE TABLE vendor_services (
    service_id VARCHAR(20) PRIMARY KEY,  -- Format: VENDOR-SERVICE, e.g., GOOGL-ADS
    vendor_id VARCHAR(10) NOT NULL REFERENCES vendors(vendor_id),
    service_name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending_confirmation' CHECK (status IN ('active', 'pending_confirmation')),
    created_by INT REFERENCES users(user_id),
    confirmed_by INT REFERENCES users(user_id),
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (vendor_id, service_name)
);
```

### 1.5 Description-Vendor Map (Cache)

```sql
CREATE TABLE description_vendor_map (
    map_id SERIAL PRIMARY KEY,
    description_pattern VARCHAR(255) NOT NULL UNIQUE,  -- Normalized key from raw_description
    vendor_id VARCHAR(10) NOT NULL REFERENCES vendors(vendor_id),
    service_id VARCHAR(20) REFERENCES vendor_services(service_id),
    city VARCHAR(100),
    state VARCHAR(50),
    country VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_desc_vendor_map_pattern ON description_vendor_map (description_pattern);
```

**Purpose:** Cache layer for vendor resolution. Once a raw description pattern has been resolved to a vendor (either by LLM or by user confirmation), the mapping is stored here. Future transactions with the same or similar description hit this cache instead of the LLM. Over time, LLM calls for vendor resolution approach zero.

**Pattern normalization:** The `description_pattern` is derived from `raw_description` by: uppercase, strip trailing whitespace, collapse multiple spaces. This ensures "GOOGLE *ADS336008342CC@GOOGLE.COM       CA" and "GOOGLE *ADS336008342CC@GOOGLE.COM  CA" resolve to the same cache key.

### 1.6 Classification Rules

```sql
CREATE TABLE classification_rules (
    rule_id SERIAL PRIMARY KEY,
    vendor_id VARCHAR(10) REFERENCES vendors(vendor_id),
    service_id VARCHAR(20) REFERENCES vendor_services(service_id),
    amount_min DECIMAL(12,2),
    amount_max DECIMAL(12,2),
    time_of_month_start INT CHECK (time_of_month_start BETWEEN 1 AND 31),
    time_of_month_end INT CHECK (time_of_month_end BETWEEN 1 AND 31),
    gl_code INT NOT NULL REFERENCES gl_codes(gl_code),
    is_active BOOLEAN DEFAULT TRUE,
    created_by INT REFERENCES users(user_id),  -- NULL if system-generated
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 1.7 Transactions (Versioned)

```sql
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(50) NOT NULL,  -- Logical ID, shared across versions
    version INT NOT NULL DEFAULT 1,
    date DATE NOT NULL,
    raw_description TEXT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    vendor_id VARCHAR(10) REFERENCES vendors(vendor_id),
    service_id VARCHAR(20) REFERENCES vendor_services(service_id),
    city VARCHAR(100),
    state VARCHAR(50),
    country VARCHAR(100),
    is_expense BOOLEAN DEFAULT TRUE,
    gl_code INT REFERENCES gl_codes(gl_code),
    confidence VARCHAR(10) CHECK (confidence IN ('High', 'Medium', 'Low')),
    method VARCHAR(20) CHECK (method IN ('Rule Match', 'LLM Inference', 'Unclassifiable')),
    rule_id INT REFERENCES classification_rules(rule_id),
    reasoning TEXT,
    review_status VARCHAR(20) DEFAULT 'Unreviewed' CHECK (review_status IN ('Unreviewed', 'Approved', 'Reclassified', 'Flagged')),
    reviewed_by INT REFERENCES users(user_id),
    reviewed_at TIMESTAMP,
    source_file VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (transaction_id, version)
);

-- Index for efficient "current version" queries
CREATE INDEX idx_transactions_current ON transactions (transaction_id, version DESC);

-- View for current transaction state
CREATE VIEW current_transactions AS
SELECT DISTINCT ON (transaction_id) *
FROM transactions
ORDER BY transaction_id, version DESC;
```

---

## 2. Preload Data — Vendors & Rules

### 2.1 Vendor Seeding

These vendors are derived from classified.csv and gl_code_dictionary.csv. Set all to status = 'active' for the demo.

```sql
INSERT INTO vendors (vendor_id, vendor_name, status) VALUES
-- Vendors from classified.csv transaction patterns
('GOOGL', 'Google', 'active'),
('MAILCH', 'Mailchimp', 'active'),
('INSXDT', 'InsuranceXDate', 'active'),
('BETTRM', 'Betterment', 'active'),
('RICONO', 'Ricono Accounting', 'active'),
('ASCEND', 'Ascend Payments', 'active'),
('ATLOFF', 'Atlanta Office Technology', 'active'),
('MDTECH', 'MedTech Consultants', 'active'),
('INDEED', 'Indeed', 'active'),
('VSP', 'VSP', 'active'),
('IDEMIA', 'IDEMIA', 'active'),
('BRADY', 'Brady Pest Control', 'active'),
('DOMAIN', 'Domain.com', 'active'),
('SIRCON', 'Vertafore Sircon', 'active'),
('MONedu', 'MonitorEDU', 'active'),
('VUE', 'Pearson VUE', 'active'),
('GABPMS', 'Georgia Baptist Mission', 'active'),
('PROFIN', 'Professional Insurance Agents', 'active'),
('USPS', 'USPS', 'active'),
('WALMRT', 'Walmart', 'active'),
('AMAZON', 'Amazon', 'active'),
('KUDOBD', 'Kudoboard', 'active'),
('HOBBY', 'Hobby Lobby', 'active'),
('POPSHL', 'PopShelf', 'active'),
('DLRTEE', 'Dollar Tree', 'active'),
('KROGER', 'Kroger', 'active'),
('WALGRN', 'Walgreens', 'active'),
('VSTAPR', 'VistaPrint', 'active'),
('DRDSH', 'DoorDash', 'active'),
('HUEYMS', 'Huey Magoos', 'active'),
('BRCOFF', 'Black Rifle Coffee', 'active'),
('CHKFLA', 'Chick-fil-A', 'active'),
('GRTHVT', 'Great Harvest Bread', 'active'),
('ATHGYR', 'Athena''s Gyros', 'active'),
('RRTACO', 'RReal Tacos', 'active'),
('CITYBB', 'City BBQ', 'active'),
('SUKI', 'Suki', 'active'),
('CHILIS', 'Chili''s', 'active'),
('DOMINO', 'Domino''s', 'active'),
('GRAYSC', 'Grayson Sweet Home Cafe', 'active'),
('MRTACO', 'Mr. Taco', 'active'),
('ELRNCH', 'El Ranchero', 'active'),
('AMPROF', 'America''s Professor', 'active'),
('MSFT', 'Microsoft', 'active'),
('CANOPY', 'Canopy (UseCanopy)', 'active'),
('OPENAI', 'OpenAI', 'active'),
('APEX', 'Apex Software', 'active'),
('ADOBE', 'Adobe', 'active'),
('DOCSIG', 'DocuSign', 'active'),
('ATT', 'AT&T', 'active'),
('COMCST', 'Comcast', 'active'),
('WALTEM', 'Walton EMC', 'active'),
('HERTZ', 'Hertz', 'active'),
('HAMPTN', 'Hampton Inn', 'active'),
('HILTON', 'Hilton', 'active'),
('EXXON', 'ExxonMobil', 'active'),
('ORBITZ', 'Orbitz', 'active'),
('TAILWD', 'Tailwind', 'active'),
('ATLBRV', 'Atlanta Braves', 'active'),
('RSCANE', 'Raising Cane''s', 'active'),
('DTCHBR', 'Dutch Bros', 'active'),
('CHECKR', 'Checkr', 'active'),
-- Additional vendors from gl_code_dictionary not in transaction history
('KLAVYO', 'Klaviyo', 'active'),
('CAMPBL', 'Campbell Group', 'active'),
('FIGLEF', 'Fig Leaf Advisor', 'active'),
('BRHALL', 'Brandon Hall', 'active'),
('OOFAKD', 'One Of A Kind', 'active'),
('GUSTO', 'Gusto', 'active'),
('SHELTN', 'Shelton & Associates', 'active'),
('SLTKLN', 'Slotkin Law', 'active'),
('ALICOR', 'Alicor', 'active'),
('HUMINT', 'Human Interest', 'active'),
('JUANA', 'Juana Alfaro', 'active'),
('RECOAT', 'Reco Atlanta Glass', 'active'),
('TALOGY', 'Talogy Caliper', 'active'),
('TOTCSR', 'Total CSR', 'active'),
('CITYOL', 'City of Loganville', 'active'),
('NIPR', 'NIPR', 'active'),
('CLB', 'CLB GA Insurance', 'active'),
('LINKDN', 'LinkedIn', 'active'),
('FEDEX', 'FedEx', 'active'),
('STAMPS', 'Stamps.com', 'active'),
('ALDI', 'Aldi', 'active'),
('HOMEDP', 'Home Depot', 'active'),
('LOWES', 'Lowe''s', 'active'),
('MARLIN', 'Marlin Copier', 'active'),
('OFFDPT', 'Office Depot', 'active'),
('OFFMAX', 'Office Max', 'active'),
('PERCON', 'Personnel Concepts', 'active'),
('PUBLIX', 'Publix', 'active'),
('QUILL', 'Quill', 'active'),
('SAMSCLB', 'Sam''s Club', 'active'),
('TJMAX', 'TJ Maxx', 'active'),
('UHAUL', 'U-Haul', 'active'),
('ZOOM', 'Zoom', 'active'),
('RINGCN', 'Ring Central', 'active'),
('FLASHE', 'Flash Electric', 'active'),
('UTICA', 'Utica National', 'active'),
('PRNCPL', 'Principal Life', 'active'),
('PROTLF', 'Protective Life', 'active'),
('PPLKEP', 'PeopleKeep', 'active'),
('HRTFRD', 'The Hartford', 'active'),
('ZAXBYS', 'Zaxby''s', 'active'),
('MARITZ', 'Maritz Global', 'active'),
('DELTCU', 'Delta Community CU', 'active'),
('IRS', 'Internal Revenue Service', 'active'),
('APPLDS', 'Applied Systems', 'active');
```

### 2.2 Vendor Services Seeding

```sql
INSERT INTO vendor_services (service_id, vendor_id, service_name, status) VALUES
-- Google services
('GOOGL-ADS', 'GOOGL', 'Google Ads', 'active'),
('GOOGL-ONE', 'GOOGL', 'Google One', 'active'),
('GOOGL-APPS', 'GOOGL', 'Google Apps/Workspace', 'active'),
-- Comcast services
('COMCST-INT', 'COMCST', 'Comcast Internet', 'active'),
('COMCST-CBL', 'COMCST', 'Comcast Cable/TV', 'active'),
-- DoorDash restaurants (as services)
('DRDSH-CUBBY', 'DRDSH', 'Cubby''s', 'active'),
('DRDSH-MCDNL', 'DRDSH', 'McDonald''s', 'active'),
('DRDSH-CHPTL', 'DRDSH', 'Chipotle', 'active'),
('DRDSH-BNDBU', 'DRDSH', 'Bandana Burgers', 'active'),
('DRDSH-CHKFL', 'DRDSH', 'Chick-fil-A', 'active'),
('DRDSH-CHILI', 'DRDSH', 'Chili''s', 'active'),
('DRDSH-LOSRB', 'DRDSH', 'Los Aribenos', 'active'),
('DRDSH-MIGEL', 'DRDSH', 'Miguel''s', 'active'),
('DRDSH-SMOKE', 'DRDSH', 'The Smokey Pig', 'active'),
-- Microsoft services
('MSFT-365', 'MSFT', 'Microsoft 365', 'active'),
('MSFT-AZURE', 'MSFT', 'Microsoft Azure', 'active'),
-- VSP services
('VSP-WRKWSE', 'VSP', 'VSP Workwise Compliance', 'active'),
-- Amazon services
('AMAZON-PRM', 'AMAZON', 'Amazon Prime', 'active'),
('AMAZON-MKT', 'AMAZON', 'Amazon Marketplace', 'active'),
-- Mailchimp
('MAILCH-MKTG', 'MAILCH', 'Mailchimp Marketing Platform', 'active'),
-- OpenAI
('OPENAI-CGPT', 'OPENAI', 'ChatGPT Subscription', 'active'),
-- Adobe
('ADOBE-PRO', 'ADOBE', 'Adobe Creative Suite', 'active'),
-- Fig Leaf (dual purpose: consulting and rent)
('FIGLEF-CONS', 'FIGLEF', 'Consulting Services', 'active'),
('FIGLEF-RENT', 'FIGLEF', 'Office Rent', 'active'),
-- AT&T
('ATT-FIBER', 'ATT', 'AT&T Fiber/Uverse', 'active'),
-- Walton EMC
('WALTEM-ELEC', 'WALTEM', 'Electric Service', 'active');
```

### 2.3 Classification Rules Seeding

These rules are derived from gl_code_dictionary.csv cross-referenced with classified.csv patterns. They represent the deterministic layer — the "cheat sheet" translated into executable rules.

```sql
INSERT INTO classification_rules (vendor_id, service_id, amount_min, amount_max, time_of_month_start, time_of_month_end, gl_code, is_active) VALUES
-- 5030 Marketing & Advertising
('GOOGL', 'GOOGL-ADS', NULL, NULL, NULL, NULL, 5030, TRUE),
('INSXDT', NULL, NULL, NULL, NULL, NULL, 5030, TRUE),
('KLAVYO', NULL, NULL, NULL, NULL, NULL, 5030, TRUE),
('MARITZ', NULL, NULL, NULL, NULL, NULL, 5030, TRUE),

-- 5100 Consulting Services
('CAMPBL', NULL, NULL, NULL, NULL, NULL, 5100, TRUE),
('FIGLEF', 'FIGLEF-CONS', NULL, NULL, NULL, NULL, 5100, TRUE),
('BRHALL', NULL, NULL, NULL, NULL, NULL, 5100, TRUE),

-- 5215 Telemarketing
('OOFAKD', NULL, NULL, NULL, NULL, NULL, 5215, TRUE),

-- 6020 Payroll Taxes
('GUSTO', NULL, NULL, NULL, NULL, NULL, 6020, TRUE),  -- Note: Gusto also maps to 6030. This rule covers payroll taxes. May need service-level differentiation.

-- 6040 401K Administration
('BETTRM', NULL, NULL, NULL, NULL, NULL, 6040, TRUE),

-- 6100 Accounting
('SHELTN', NULL, NULL, NULL, NULL, NULL, 6100, TRUE),
('RICONO', NULL, NULL, NULL, NULL, NULL, 6100, TRUE),

-- 6110 Legal
('SLTKLN', NULL, NULL, NULL, NULL, NULL, 6110, TRUE),

-- 6115 Outside Services
('ALICOR', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('ASCEND', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('ATLOFF', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('HUMINT', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('INDEED', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('JUANA', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('MDTECH', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('RECOAT', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('TALOGY', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('TOTCSR', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('VSP', 'VSP-WRKWSE', NULL, NULL, NULL, NULL, 6115, TRUE),
('IDEMIA', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('BRADY', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),
('DOMAIN', NULL, NULL, NULL, NULL, NULL, 6115, TRUE),

-- 6120 Licenses & Permits
('SIRCON', NULL, NULL, NULL, NULL, NULL, 6120, TRUE),
('CITYOL', NULL, NULL, NULL, NULL, NULL, 6120, TRUE),
('NIPR', NULL, NULL, NULL, NULL, NULL, 6120, TRUE),
('CLB', NULL, NULL, NULL, NULL, NULL, 6120, TRUE),
('MONedu', NULL, NULL, NULL, NULL, NULL, 6120, TRUE),
('VUE', NULL, NULL, NULL, NULL, NULL, 6120, TRUE),

-- 6130 Dues & Subscriptions
('LINKDN', NULL, NULL, NULL, NULL, NULL, 6130, TRUE),
('GOOGL', 'GOOGL-ONE', NULL, NULL, NULL, NULL, 6130, TRUE),
('GOOGL', 'GOOGL-APPS', NULL, NULL, NULL, NULL, 6130, TRUE),
('GABPMS', NULL, NULL, NULL, NULL, NULL, 6130, TRUE),
('PROFIN', NULL, NULL, NULL, NULL, NULL, 6130, TRUE),

-- 6140 Postage
('USPS', NULL, NULL, NULL, NULL, NULL, 6140, TRUE),
('FEDEX', NULL, NULL, NULL, NULL, NULL, 6140, TRUE),
('STAMPS', NULL, NULL, NULL, NULL, NULL, 6140, TRUE),

-- 6160 Office Supplies & Expenses
('WALMRT', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('AMAZON', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('HOBBY', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('HOMEDP', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('KROGER', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('LOWES', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('MARLIN', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('OFFDPT', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('OFFMAX', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('PERCON', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('PUBLIX', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('QUILL', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('SAMSCLB', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('TJMAX', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('UHAUL', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('VSTAPR', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('ALDI', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('KUDOBD', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('POPSHL', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('DLRTEE', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),
('WALGRN', NULL, NULL, NULL, NULL, NULL, 6160, TRUE),

-- 6170 Travel Meals Entertainment - Admin
('DRDSH', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('HUEYMS', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('BRCOFF', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('CHKFLA', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('GRTHVT', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('ATHGYR', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('RRTACO', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('CITYBB', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('SUKI', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('CHILIS', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('DOMINO', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('GRAYSC', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('MRTACO', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('ELRNCH', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('ZAXBYS', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('RSCANE', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('DTCHBR', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('HERTZ', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('HAMPTN', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('HILTON', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('EXXON', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('ORBITZ', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('TAILWD', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),
('ATLBRV', NULL, NULL, NULL, NULL, NULL, 6170, TRUE),

-- 6180 Education & Training
('AMPROF', NULL, NULL, NULL, NULL, NULL, 6180, TRUE),

-- 6200 Computer Internet & Software
('MSFT', NULL, NULL, NULL, NULL, NULL, 6200, TRUE),
('CANOPY', NULL, NULL, NULL, NULL, NULL, 6200, TRUE),
('OPENAI', NULL, NULL, NULL, NULL, NULL, 6200, TRUE),
('APEX', NULL, NULL, NULL, NULL, NULL, 6200, TRUE),
('ADOBE', NULL, NULL, NULL, NULL, NULL, 6200, TRUE),
('DOCSIG', NULL, NULL, NULL, NULL, NULL, 6200, TRUE),
('ZOOM', NULL, NULL, NULL, NULL, NULL, 6200, TRUE),
('APPLDS', NULL, NULL, NULL, NULL, NULL, 6200, TRUE),
('COMCST', 'COMCST-INT', NULL, NULL, NULL, NULL, 6200, TRUE),

-- 6210 Insurance Expense
('UTICA', NULL, NULL, NULL, NULL, NULL, 6210, TRUE),
('PRNCPL', NULL, NULL, NULL, NULL, NULL, 6210, TRUE),
('PROTLF', NULL, NULL, NULL, NULL, NULL, 6210, TRUE),
('PPLKEP', NULL, NULL, NULL, NULL, NULL, 6210, TRUE),
('HRTFRD', NULL, NULL, NULL, NULL, NULL, 6210, TRUE),

-- 6240 Rent
('FIGLEF', 'FIGLEF-RENT', NULL, NULL, NULL, NULL, 6240, TRUE),

-- 6250 Telephone
('ATT', NULL, NULL, NULL, NULL, NULL, 6250, TRUE),
('RINGCN', NULL, NULL, NULL, NULL, NULL, 6250, TRUE),

-- 6260 Utilities
('COMCST', 'COMCST-CBL', NULL, NULL, NULL, NULL, 6260, TRUE),
('WALTEM', NULL, NULL, NULL, NULL, NULL, 6260, TRUE),
('FLASHE', NULL, NULL, NULL, NULL, NULL, 6260, TRUE);
```

**Notable design decisions in rules:**
- **Mailchimp** is NOT given a rule. Historical data shows it split between 5030 and 6200 with identical descriptions and amounts. This is genuinely ambiguous — the LLM layer should flag it as Low confidence for user review.
- **Comcast** is split by service: Internet → 6200, Cable → 6260. Vendor resolution must correctly identify the service.
- **Google** is split by service: Ads → 5030, One → 6130, Apps → 6130.
- **Fig Leaf** is split by service: Consulting → 5100, Rent → 6240.
- **Kudoboard** appears in both 6160 and 6170 historically. Defaulting to 6160 (more common). May need reclassification.
- **Gusto** maps to both 6020 and 6030 in the dictionary. Single rule for 6020; may need service differentiation.
- **CHECKR** is coded 6170 in classified.csv but is actually a background check service — this is likely a historical misclassification. The LLM layer should catch this.

---

## 3. Classification Pipeline

### 3.1 Phase 1 — Vendor Resolution (Cache-First)

Vendor resolution maps raw transaction descriptions to structured vendor/service/location data. It uses a **cache-first** architecture: check the `description_vendor_map` table before making any LLM calls. LLM is only invoked for genuinely unseen description patterns.

**Step 1: Normalize and cache lookup**

```python
def normalize_description(raw: str) -> str:
    """Normalize raw description to a cache key."""
    return ' '.join(raw.upper().strip().split())

def resolve_vendors_batch(transactions):
    """
    Resolve vendors for a batch of transactions.
    Cache-first: only call LLM for descriptions not in description_vendor_map.
    """
    # 1. Normalize all descriptions
    for txn in transactions:
        txn.description_pattern = normalize_description(txn.raw_description)

    # 2. Deduplicate — only need to resolve each unique pattern once
    unique_patterns = set(txn.description_pattern for txn in transactions)

    # 3. Check cache for all unique patterns
    cached = query_description_vendor_map(unique_patterns)
    uncached_patterns = unique_patterns - set(cached.keys())

    # 4. Send ALL uncached patterns to LLM in a single call
    if uncached_patterns:
        llm_results = resolve_via_llm(list(uncached_patterns))
        # 5. Write new mappings to cache
        for pattern, result in llm_results.items():
            insert_description_vendor_map(pattern, result)
        cached.update(llm_results)

    # 6. Apply resolved vendor data back to all transactions
    for txn in transactions:
        mapping = cached[txn.description_pattern]
        txn.vendor_id = mapping.vendor_id
        txn.service_id = mapping.service_id
        txn.city = mapping.city
        txn.state = mapping.state
        txn.country = mapping.country
```

**Step 2: LLM call for uncached descriptions (single call)**

All uncached unique descriptions are sent in one API call. The full dataset (both CSVs combined) has ~150-180 unique descriptions. After deduplication and cache lookup, the uncached set will be smaller. Even in a cold-start scenario with zero cache, the entire payload fits comfortably in a single call:

- ~180 unique descriptions × ~50 chars = ~9,000 chars ≈ ~2,500 tokens
- Known vendor/service reference list ≈ ~2,500 tokens
- System prompt + response schema ≈ ~500 tokens
- Full JSON response for 180 descriptions ≈ ~8,000 tokens
- **Total: ~13,500 tokens — one call, well within context limits**

**LLM Prompt Design:**

```
System: You are a financial transaction parser. Extract vendor information from credit card transaction descriptions.

You will receive:
1. A list of raw transaction descriptions (deduplicated)
2. A list of known vendors and their services from our database

For EACH description:
- Match to a known vendor if possible. Use fuzzy matching — descriptions are messy and truncated.
- If the vendor is not in the known list, suggest a new vendor_id (uppercase, max 10 chars) and vendor_name.
- Identify the specific service if applicable (e.g., "GOOGLE *ADS..." → vendor: GOOGL, service: GOOGL-ADS)
- Extract city and state from the description if present. Infer country from city/state.

Respond in JSON only — an array with one entry per description, in the same order as input:
[
  {
    "description_pattern": "GOOGLE *ADS336008342CC@GOOGLE.COM CA",
    "vendor_id": "GOOGL",
    "vendor_name": "Google",
    "is_new_vendor": false,
    "service_id": "GOOGL-ADS",
    "service_name": "Google Ads",
    "is_new_service": false,
    "city": null,
    "state": "CA",
    "country": "US"
  },
  ...
]
```

**Cost profile at scale:**
- First run (cold cache): 1 LLM call resolves all unique descriptions. Results cached.
- Subsequent runs: only new/unseen descriptions hit the LLM. For a business with stable vendors, this is single-digit percent of transactions within a few months.
- Steady state: near-zero LLM cost for vendor resolution. Cost shifts entirely to GL classification for rule-unmatched transactions.

**For the demo:** Run vendor resolution for classified.csv first (populates the cache), then classify.csv benefits from the cache immediately — most vendors will already be mapped. Auto-confirm all vendors from classified.csv (status = 'active'). Vendors first seen in classify.csv remain 'pending_confirmation'.

### 3.2 Phase 2 — GL Classification

**Step 1: Deterministic Layer**

```python
def classify_deterministic(transaction, rules):
    """
    Match transaction against active rules.
    Returns (gl_code, confidence, rule_id, reasoning) or None if no match.
    """
    matching_rules = []
    for rule in rules:
        if rule.vendor_id != transaction.vendor_id:
            continue
        if rule.service_id and rule.service_id != transaction.service_id:
            continue
        if rule.amount_min and transaction.amount < rule.amount_min:
            continue
        if rule.amount_max and transaction.amount > rule.amount_max:
            continue
        if rule.time_of_month_start and rule.time_of_month_end:
            day = transaction.date.day
            if not (rule.time_of_month_start <= day <= rule.time_of_month_end):
                continue
        matching_rules.append(rule)

    if len(matching_rules) == 0:
        return None  # Route to LLM
    elif len(matching_rules) == 1:
        rule = matching_rules[0]
        return {
            'gl_code': rule.gl_code,
            'confidence': 'High',
            'method': 'Rule Match',
            'rule_id': rule.rule_id,
            'reasoning': f'Rule R-{rule.rule_id}: Vendor {rule.vendor_id}'
                         + (f', Service {rule.service_id}' if rule.service_id else '')
                         + (f', Amount ${rule.amount_min}-${rule.amount_max}' if rule.amount_min else '')
                         + f' → GL {rule.gl_code}'
        }
    else:
        # Multiple matching rules with potentially different GL codes
        gl_codes = set(r.gl_code for r in matching_rules)
        if len(gl_codes) == 1:
            # Multiple rules, same GL code — still High confidence
            rule = matching_rules[0]  # Use most specific
            return {
                'gl_code': rule.gl_code,
                'confidence': 'High',
                'method': 'Rule Match',
                'rule_id': rule.rule_id,
                'reasoning': f'Rule R-{rule.rule_id}: matched ({len(matching_rules)} rules, consistent GL {rule.gl_code})'
            }
        else:
            # Conflict — flag for review
            conflict_detail = ', '.join([f'R-{r.rule_id}→GL {r.gl_code}' for r in matching_rules])
            return {
                'gl_code': matching_rules[0].gl_code,  # Best guess: most specific
                'confidence': 'Low',
                'method': 'Rule Match',
                'rule_id': None,
                'reasoning': f'RULE CONFLICT: {conflict_detail}. Flagged for review.',
                'review_status': 'Flagged'
            }
```

**Rule specificity ordering:** When multiple rules match, prefer: vendor + service + amount > vendor + service > vendor + amount > vendor only.

**Step 2: LLM Inference Layer**

For transactions with no rule match, batch ALL of them into a single LLM call (same principle as vendor resolution — minimize API calls).

```
System: You are a GL code classifier for a small insurance agency.
You will receive a batch of transactions that could not be classified by deterministic rules, along with context to help you assign the correct GL codes.

Rules:
- Assign exactly one GL code from the provided hierarchy for each transaction.
- Assess your confidence per transaction: "Medium" if you have reasonable supporting evidence, "Low" if uncertain.
- If you truly cannot classify a transaction, return gl_code as null and confidence as "Low".
- Be conservative. When uncertain between two codes, choose "Low" confidence and explain the ambiguity.
- Negative amounts may be refunds/credits. Classify based on the nature of the expense, not the cash direction.

Respond in JSON only — an array with one entry per transaction, in the same order as input:
[
  {
    "transaction_id": "NEW-042",
    "gl_code": 6160,
    "confidence": "Medium",
    "reasoning": "Vendor POPSHELF is a retail store similar to Dollar Tree. Amount $12.47 is consistent with office supplies. 3 similar transactions in history coded to 6160."
  },
  ...
]

User:
Transactions to classify:
{array of transactions: transaction_id, date, raw_description, amount, vendor_id, vendor_name, service_id, service_name, city, state}

Historical comparables (grouped by vendor, up to 10 per vendor):
{similar transactions with their GL codes}

GL Code Reference:
{gl_codes table — level 3 codes with descriptions}
```

**Finding historical comparables:**
- First, query by vendor_id from current_transactions view (classified.csv data)
- If fewer than 5 results, expand search by fuzzy description matching (trigram similarity on raw_description)
- Include the GL code, amount, and date for each comparable

### 3.3 Non-Expense Detection

Run BEFORE vendor resolution. Simple deterministic check:

```python
def is_non_expense(description: str, amount: float) -> bool:
    non_expense_keywords = ['AUTOPAY PAYMENT', 'PAYMENT - THANK YOU']
    description_upper = description.upper().strip()
    for keyword in non_expense_keywords:
        if keyword in description_upper:
            return True
    return False
```

Transactions flagged as non-expense: set `is_expense = FALSE`, skip classification pipeline entirely, set `gl_code = NULL`, `method = 'Unclassifiable'`, `confidence = NULL`, `reasoning = 'Non-expense transaction: credit card payment'`, `review_status = 'Approved'`.

---

## 4. API Layer (FastAPI)

### 4.1 Project Structure

```
backend/
├── main.py                  # FastAPI app, CORS, startup
├── database.py              # SQLAlchemy engine, session
├── models.py                # SQLAlchemy ORM models
├── schemas.py               # Pydantic request/response schemas
├── routers/
│   ├── transactions.py      # /api/transactions/*
│   ├── rules.py             # /api/rules/*
│   ├── vendors.py           # /api/vendors/*
│   ├── gl_codes.py          # /api/gl-codes/*
│   └── classify.py          # /api/classify/*
├── services/
│   ├── classification.py    # Classification pipeline orchestration
│   ├── vendor_resolution.py # Cache-first vendor resolution + LLM fallback
│   ├── vendor_cache.py      # description_vendor_map CRUD operations
│   ├── rule_engine.py       # Deterministic rule matching
│   └── llm_classifier.py    # LLM GL code inference
├── seed.py                  # Database seeding script
└── requirements.txt
```

### 4.2 Endpoints

**Transactions:**
- `GET /api/transactions` — List with query params: `confidence`, `gl_code`, `review_status`, `vendor_id`, `date_from`, `date_to`, `sort_by`, `sort_order`, `page`, `page_size`. Always returns current version only (from `current_transactions` view).
- `GET /api/transactions/{transaction_id}` — Single transaction with all versions.
- `POST /api/transactions/{transaction_id}/approve` — Creates new version: review_status = 'Approved', reviewed_by, reviewed_at. Body: `{ user_id }`.
- `POST /api/transactions/{transaction_id}/reclassify` — Creates new version with updated gl_code, confidence = 'High', method preserved or set to 'Rule Match' if from rule, review_status = 'Reclassified'. Body: `{ gl_code, user_id, notes }`.
- `POST /api/transactions/{transaction_id}/flag` — Creates new version: review_status = 'Flagged'. Body: `{ user_id, notes }`.
- `POST /api/transactions/{transaction_id}/convert-to-rule` — Creates a classification rule from transaction attributes. Body: `{ vendor_id, service_id, amount_min, amount_max, time_of_month_start, time_of_month_end, gl_code, user_id }`. Prepopulates from transaction data, user can override.

**Rules:**
- `GET /api/rules` — List all rules with match statistics (count of transactions classified by each rule).
- `POST /api/rules` — Create rule. Body: `{ vendor_id, service_id, amount_min, amount_max, time_of_month_start, time_of_month_end, gl_code, user_id }`. Validate no exact duplicate exists. Warn on overlap (return 409 with conflict details if overlapping rule with different GL code exists).
- `PUT /api/rules/{rule_id}` — Update rule.
- `POST /api/rules/{rule_id}/deactivate` — Set is_active = FALSE.

**Vendors:**
- `GET /api/vendors` — List with optional `?search=` for autocomplete. Returns vendors with service count and transaction count.
- `POST /api/vendors` — Create vendor. Body: `{ vendor_id, vendor_name, user_id }`.
- `PUT /api/vendors/{vendor_id}` — Update vendor.
- `POST /api/vendors/{vendor_id}/confirm` — Set status = 'active', confirmed_by, confirmed_at. Body: `{ user_id }`.
- `GET /api/vendors/{vendor_id}/services` — List services for vendor.
- `POST /api/vendors/{vendor_id}/services` — Create service. Body: `{ service_id, service_name, user_id }`.

**GL Codes:**
- `GET /api/gl-codes` — Full hierarchy. Returns nested structure: Level 1 → Level 2 → Level 3.
- `GET /api/gl-codes?level=3` — Flat list of operational codes only (for dropdowns).

**Classification:**
- `POST /api/classify` — Trigger classification pipeline. Body: `{ source_file }` (optional filter). Returns job status with summary: total transactions, classified by rule, classified by LLM, unclassifiable, non-expense.
- `GET /api/classify/status` — Pipeline run status.

**Dashboard Stats (for UI summary bar):**
- `GET /api/stats` — Returns: total transactions, by review status, by confidence, by method, by GL code.

---

## 5. Frontend (React)

### 5.1 Project Structure

```
frontend/
├── src/
│   ├── App.jsx
│   ├── api/                   # API client functions
│   │   └── client.js
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.jsx    # Navigation
│   │   │   └── Header.jsx
│   │   ├── transactions/
│   │   │   ├── TransactionTable.jsx
│   │   │   ├── TransactionRow.jsx
│   │   │   ├── ReclassifyModal.jsx
│   │   │   ├── ConvertToRuleModal.jsx
│   │   │   └── TransactionFilters.jsx
│   │   ├── rules/
│   │   │   ├── RulesTable.jsx
│   │   │   ├── RuleForm.jsx
│   │   │   └── RuleConflictWarning.jsx
│   │   ├── vendors/
│   │   │   ├── VendorTable.jsx
│   │   │   ├── VendorDetail.jsx
│   │   │   └── VendorConfirmBanner.jsx
│   │   ├── gl/
│   │   │   ├── GLHierarchyPanel.jsx     # Tree view for reference
│   │   │   └── GLCodeSelector.jsx       # Dropdown grouped by hierarchy
│   │   └── shared/
│   │       ├── DataTable.jsx            # Reusable sortable/filterable table
│   │       ├── Badge.jsx                # Confidence/status badges
│   │       ├── AutocompleteInput.jsx    # For vendor/service selection
│   │       └── StatsBar.jsx             # Summary statistics bar
│   ├── pages/
│   │   ├── TransactionsPage.jsx
│   │   ├── RulesPage.jsx
│   │   ├── VendorsPage.jsx
│   │   └── GLReferencePage.jsx
│   └── hooks/
│       ├── useTransactions.js
│       ├── useRules.js
│       └── useVendors.js
```

### 5.2 UI Design Guidelines

**Layout:**
- Left sidebar navigation: Transactions (default), Rules, Vendors, GL Reference
- Top summary stats bar on Transactions page: Total | Unreviewed | High Confidence | Medium | Low | Flagged

**Transaction Table:**
- Columns: Date | Description | Amount | Vendor | Service | GL Code | Confidence | Method | Reasoning (truncated, expandable) | Review Status | Actions
- Confidence badges: High = green, Medium = yellow, Low = red
- Review status badges: Unreviewed = gray, Approved = green, Reclassified = blue, Flagged = red
- Row actions: Approve (✓), Reclassify (pencil icon), Flag (🚩), Convert to Rule (→R)
- Default sort: Unreviewed first, then confidence Low → Medium → High
- Non-expense transactions displayed in a separate section or with a distinct visual treatment (gray/muted)
- Clicking a row expands to show full reasoning + version history

**Reclassify Modal:**
- GL code dropdown grouped by hierarchy (Level 1 header → Level 2 header → Level 3 selectable items)
- Shows current assignment and reasoning
- Optional notes field
- "Also create a rule for this?" checkbox → opens Convert to Rule flow

**Convert to Rule Modal:**
- Prepopulated from transaction: Vendor (autocomplete), Service (autocomplete, filtered by vendor), Amount range (default: ±20% of transaction amount), Time of month (optional), GL Code
- Shows existing rules for the selected vendor to help user check for conflicts
- On save, validates against existing rules and warns on overlap

**Rules Table:**
- Columns: Rule ID | Vendor | Service | Amount Range | Time of Month | GL Code | Status | Match Count | Created Date
- Actions: Edit, Deactivate
- Create Rule button opens the Rule Form
- Inactive rules shown at bottom, grayed out

**Vendor Table:**
- Columns: Vendor ID | Name | Status | Services (count) | Transactions (count) | Created Date
- Pending confirmation vendors highlighted with yellow banner at top
- Expandable rows showing services
- Actions: Edit, Confirm (for pending), Add Service

**GL Reference Page:**
- Tree view: Level 1 → Level 2 → Level 3 with descriptions
- Searchable
- Read-only

### 5.3 Key UX Interactions

**Approval flow:**
1. User clicks Approve on a transaction row
2. System creates new version with review_status = 'Approved'
3. If vendor status is 'pending_confirmation', prompt user to also confirm the vendor
4. Row updates in place, moves down in default sort

**Reclassify flow:**
1. User clicks Reclassify → modal opens with GL hierarchy selector
2. User selects new GL code
3. Modal prompts: "Create a rule for future [Vendor] transactions?"
4. If yes → Convert to Rule modal opens prepopulated
5. New transaction version created with updated GL code, confidence = 'High'

**Convert to Rule (standalone):**
1. User clicks Convert to Rule on any transaction
2. Modal opens prepopulated with transaction attributes
3. User adjusts as needed, saves
4. System checks for conflicts, warns if overlap
5. Rule created, transaction NOT automatically reclassified (rule applies to future classifications)

---

## 6. Data Ingestion & Demo Initialization

### 6.1 Startup Sequence

Run via `seed.py` script:

1. **Create tables** — run all CREATE TABLE statements (including `description_vendor_map`)
2. **Seed users** — create demo user: `{ username: 'demo_user', role: 'read_write' }`
3. **Seed GL codes** — insert full hierarchy (Section 2 SQL)
4. **Seed vendors** — insert all vendors (Section 2.1 SQL)
5. **Seed vendor services** — insert all services (Section 2.2 SQL)
6. **Seed classification rules** — insert all rules (Section 2.3 SQL)
7. **Ingest classified.csv** — parse and insert into transactions table:
   - Generate transaction_id as `CLF-{row_number}` (e.g., CLF-001)
   - Parse amount: strip $, handle parenthetical negatives `($X.XX)` → `-X.XX`
   - Set source_file = 'classified.csv'
   - Set review_status = 'Approved' (these are historically confirmed)
   - Set confidence = 'High', method = 'Rule Match' (treated as ground truth)
   - Set gl_code from the CSV's 'Assigned GL Code' column
   - Run vendor resolution (cache-first): since cache is cold, all unique descriptions go to LLM in a single call. Results populate `description_vendor_map`. All resolved vendors auto-confirmed (status = 'active').
8. **Ingest classify.csv** — parse and insert into transactions table:
   - Generate transaction_id as `NEW-{row_number}` (e.g., NEW-001)
   - Same amount parsing
   - Set source_file = 'classify.csv'
   - Set review_status = 'Unreviewed'
   - Detect non-expense transactions FIRST (AUTOPAY etc.)
   - Run vendor resolution (cache-first): most descriptions will hit the cache populated in step 7. Only genuinely new vendors require an LLM call — likely a single additional call or zero if all vendors were seen in classified.csv. New vendors set to 'pending_confirmation'.
   - Run GL classification (Phase 2) — deterministic rules first, then LLM for unmatched (also a single batched call for all rule-unmatched transactions)
9. **Verify** — log summary: X transactions ingested, Y classified by rule, Z by LLM, W unclassifiable, V non-expense, N vendor cache hits, M vendor cache misses

### 6.2 CSV Parsing Notes

**classified.csv:**
- Has trailing empty columns (commas) — strip them
- Amount format: `$X.XX` or `($X.XX)` for negatives
- Description is fixed-width padded — strip whitespace
- 'Assigned GL Code' column has some NaN values — skip those rows

**classify.csv:**
- Has BOM character at start — use `encoding='utf-8-sig'` 
- Same amount format as classified.csv
- No GL code column (that's what we're assigning)

**gl_code_dictionary.csv:**
- Used for rule derivation (already handled in Section 2.3)
- Not directly ingested as a table — its information is captured in vendors, services, and rules

---

## 7. Environment & Configuration

### 7.1 Environment Variables

```
DATABASE_URL=postgresql://user:password@localhost:5432/gl_classifier
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-sonnet-4-20250514
LLM_MAX_TOKENS=8000
CORS_ORIGINS=http://localhost:5173
```

### 7.2 Docker Compose

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: gl_classifier
      POSTGRES_USER: gluser
      POSTGRES_PASSWORD: glpass
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://gluser:glpass@db:5432/gl_classifier
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    depends_on:
      - db
    volumes:
      - ./data:/app/data  # Mount CSV files

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    depends_on:
      - backend

volumes:
  pgdata:
```

### 7.3 Requirements (Python)

```
fastapi==0.115.0
uvicorn==0.30.0
sqlalchemy==2.0.35
psycopg2-binary==2.9.9
pydantic==2.9.0
anthropic==0.39.0
pandas==2.2.0
python-dotenv==1.0.0
```

---

## 8. Build Order

Execute in this order to enable incremental testing. **CHECKPOINT after Phase 2** — pause for review before proceeding to API and frontend.

### Phase 1: Foundation
1. Docker Compose with PostgreSQL
2. Database schema (all tables including `description_vendor_map`, views, indexes)
3. SQLAlchemy models
4. Seed script (GL codes, vendors, services, rules, CSV ingestion WITHOUT classification)
5. Verify: data loads cleanly, relationships intact

### Phase 2: Classification Engine
6. Non-expense detection (simple, deterministic)
7. Description-vendor map cache layer (normalize, lookup, insert)
8. Vendor resolution service (cache-first, LLM for uncached — single batched call)
9. Rule engine (deterministic matching logic)
10. LLM classifier service (GL code inference — single batched call for all rule-unmatched)
11. Classification pipeline orchestrator (ties phases together)
12. Run full pipeline: ingest classified.csv → populate vendor cache → ingest classify.csv → classify
13. Verify output: print summary table of classification results. Log cache hit rate.

**⏸ CHECKPOINT — Pause here. Review classification output before proceeding.**
- Verify: GL codes assigned match expectations for known vendors
- Verify: Non-expense transactions (AUTOPAY) correctly excluded
- Verify: Multi-code vendors (Google, Comcast) correctly split by service
- Verify: Vendor cache populated and functional
- Verify: LLM inference reasoning is sensible for rule-unmatched transactions

### Phase 3: API
14. FastAPI app with CORS
15. Transaction endpoints (GET list, GET detail, POST approve/reclassify/flag)
16. Rules endpoints (CRUD)
17. Vendor endpoints (CRUD + confirm)
18. GL codes endpoint
19. Classify endpoint (trigger pipeline)
20. Stats endpoint

### Phase 4: Frontend
21. React app scaffold (Vite + TailwindCSS + React Query)
22. Layout (sidebar, header)
23. Transaction table with filtering/sorting
24. Transaction row actions (approve, reclassify, flag)
25. Reclassify modal with GL hierarchy selector
26. Convert to Rule modal
27. Rules manager (table + create/edit form)
28. Vendor manager (table + confirm flow)
29. GL reference page (tree view)
30. Stats bar

### Phase 5: Polish
31. Error handling (API error states, loading states)
32. Edge case testing (negative amounts, non-expense, multi-code vendors)
33. README with setup instructions
