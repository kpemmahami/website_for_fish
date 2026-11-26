BEGIN;

LOCK TABLE public.alembic_version IN EXCLUSIVE MODE;
DO $$
BEGIN
    IF (SELECT count(*) FROM public.alembic_version) <> 1
       OR NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num = '0039_staff_feeding_access') THEN
        RAISE EXCEPTION 'Migration stopped. Expected the single 0039_staff_feeding_access revision.';
    END IF;
END $$;
SET LOCAL search_path TO public;


-- Running upgrade 0039_staff_feeding_access -> 0040_collection_deposits

CREATE TABLE collection_deposits (
    repayment_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    amount_pesewas INTEGER NOT NULL,
    PRIMARY KEY (repayment_id),
    CONSTRAINT ck_collection_deposit_positive CHECK (amount_pesewas > 0),
    FOREIGN KEY(repayment_id) REFERENCES loan_repayments (id),
    FOREIGN KEY(customer_id) REFERENCES users (id)
);

CREATE INDEX ix_collection_deposits_customer_id ON collection_deposits (customer_id);

UPDATE alembic_version SET version_num='0040_collection_deposits' WHERE alembic_version.version_num = '0039_staff_feeding_access';

-- Running upgrade 0040_collection_deposits -> 0041_standalone_deposits

CREATE TABLE standalone_collection_deposits (
    id SERIAL NOT NULL,
    reference VARCHAR(48) NOT NULL,
    institution_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    evidence_id INTEGER NOT NULL,
    recorded_by INTEGER NOT NULL,
    amount_pesewas INTEGER NOT NULL,
    paid_on DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_standalone_deposit_positive CHECK (amount_pesewas > 0),
    UNIQUE (reference),
    FOREIGN KEY(institution_id) REFERENCES finance_institutions (id),
    FOREIGN KEY(customer_id) REFERENCES users (id),
    UNIQUE (evidence_id),
    FOREIGN KEY(evidence_id) REFERENCES loan_evidence (id),
    FOREIGN KEY(recorded_by) REFERENCES users (id)
);

CREATE INDEX ix_standalone_collection_deposits_customer_id ON standalone_collection_deposits (customer_id);

CREATE INDEX ix_standalone_collection_deposits_institution_id ON standalone_collection_deposits (institution_id);

UPDATE alembic_version SET version_num='0041_standalone_deposits' WHERE alembic_version.version_num = '0040_collection_deposits';

-- Running upgrade 0041_standalone_deposits -> 0042_institution_branches

CREATE TABLE institution_branches (
    id SERIAL NOT NULL,
    institution_id INTEGER NOT NULL,
    code VARCHAR(24) NOT NULL,
    name VARCHAR(120) NOT NULL,
    address VARCHAR(260) NOT NULL,
    active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_institution_branch_code UNIQUE (institution_id, code),
    FOREIGN KEY(institution_id) REFERENCES finance_institutions (id)
);

UPDATE alembic_version SET version_num='0042_institution_branches' WHERE alembic_version.version_num = '0041_standalone_deposits';

-- Running upgrade 0042_institution_branches -> 0043_branch_assignments

ALTER TABLE finance_institution_members ADD COLUMN branch_id INTEGER;

ALTER TABLE finance_institution_members ADD CONSTRAINT fk_finance_institution_members_branch FOREIGN KEY(branch_id) REFERENCES institution_branches (id);

CREATE INDEX ix_finance_institution_members_branch_id ON finance_institution_members (branch_id);

ALTER TABLE loan_applications ADD COLUMN branch_id INTEGER;

ALTER TABLE loan_applications ADD CONSTRAINT fk_loan_applications_branch FOREIGN KEY(branch_id) REFERENCES institution_branches (id);

CREATE INDEX ix_loan_applications_branch_id ON loan_applications (branch_id);

UPDATE alembic_version SET version_num='0043_branch_assignments' WHERE alembic_version.version_num = '0042_institution_branches';

-- Running upgrade 0043_branch_assignments -> 0044_institution_accounting

CREATE TABLE institution_accounting_accounts (
    id SERIAL NOT NULL,
    institution_id INTEGER NOT NULL,
    code VARCHAR(32) NOT NULL,
    name VARCHAR(160) NOT NULL,
    category VARCHAR(16) NOT NULL,
    active BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_accounting_institution_code UNIQUE (institution_id, code),
    CONSTRAINT ck_accounting_account_category CHECK (category IN ('asset','liability','equity','income','expense','contra')),
    FOREIGN KEY(institution_id) REFERENCES finance_institutions (id)
);

CREATE TABLE institution_accounting_journals (
    id SERIAL NOT NULL,
    institution_id INTEGER NOT NULL,
    source_type VARCHAR(40) NOT NULL,
    source_reference VARCHAR(120) NOT NULL,
    effective_on DATE NOT NULL,
    posted_by INTEGER NOT NULL,
    posted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_accounting_journal_source UNIQUE (institution_id, source_type, source_reference),
    FOREIGN KEY(institution_id) REFERENCES finance_institutions (id),
    FOREIGN KEY(posted_by) REFERENCES users (id)
);

CREATE TABLE institution_accounting_lines (
    id SERIAL NOT NULL,
    journal_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    debit_pesewas BIGINT NOT NULL,
    credit_pesewas BIGINT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_accounting_line_one_side CHECK ((debit_pesewas > 0 AND credit_pesewas = 0) OR (credit_pesewas > 0 AND debit_pesewas = 0)),
    FOREIGN KEY(journal_id) REFERENCES institution_accounting_journals (id),
    FOREIGN KEY(account_id) REFERENCES institution_accounting_accounts (id)
);

CREATE INDEX ix_institution_accounting_lines_journal_id ON institution_accounting_lines (journal_id);

CREATE INDEX ix_institution_accounting_lines_account_id ON institution_accounting_lines (account_id);

UPDATE alembic_version SET version_num='0044_institution_accounting' WHERE alembic_version.version_num = '0043_branch_assignments';

-- Running upgrade 0044_institution_accounting -> 0045_accounting_periods

CREATE TABLE institution_accounting_periods (
    id SERIAL NOT NULL,
    institution_id INTEGER NOT NULL,
    starts_on DATE NOT NULL,
    closed BOOLEAN NOT NULL,
    changed_by INTEGER NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_accounting_period_month UNIQUE (institution_id, starts_on),
    FOREIGN KEY(institution_id) REFERENCES finance_institutions (id),
    FOREIGN KEY(changed_by) REFERENCES users (id)
);

UPDATE alembic_version SET version_num='0045_accounting_periods' WHERE alembic_version.version_num = '0044_institution_accounting';


DO $$
BEGIN
    IF (SELECT count(*) FROM public.alembic_version) <> 1
       OR NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num = '0045_accounting_periods') THEN
        RAISE EXCEPTION 'Migration verification failed. Expected 0045_accounting_periods.';
    END IF;
END $$;
COMMIT;


SELECT version_num,
       to_regclass('public.institution_branches') IS NOT NULL AS branches_ready,
       to_regclass('public.institution_accounting_journals') IS NOT NULL AS journals_ready,
       to_regclass('public.institution_accounting_periods') IS NOT NULL AS periods_ready,
       to_regclass('public.standalone_collection_deposits') IS NOT NULL AS deposits_ready
FROM public.alembic_version;
