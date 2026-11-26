BEGIN;

LOCK TABLE public.alembic_version IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
    IF (SELECT count(*) FROM public.alembic_version) <> 1
       OR NOT EXISTS (
           SELECT 1 FROM public.alembic_version
           WHERE version_num = '0045_accounting_periods'
       ) THEN
        RAISE EXCEPTION 'Migration stopped. Expected the single 0045_accounting_periods revision.';
    END IF;
END $$;

ALTER TABLE public.finance_institutions
    ADD COLUMN require_disbursement_approval BOOLEAN DEFAULT FALSE NOT NULL;

CREATE TABLE public.loan_disbursement_reviews (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER NOT NULL REFERENCES public.loan_accounts (id),
    amount_pesewas INTEGER NOT NULL,
    reference VARCHAR(100) NOT NULL,
    disbursed_on DATE NOT NULL,
    evidence_id INTEGER NOT NULL UNIQUE REFERENCES public.loan_evidence (id),
    prepared_by INTEGER NOT NULL REFERENCES public.users (id),
    status VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    decided_by INTEGER REFERENCES public.users (id),
    decided_at TIMESTAMPTZ,
    reason VARCHAR(500),
    CONSTRAINT uq_disbursement_review_reference UNIQUE (loan_id, reference),
    CONSTRAINT ck_disbursement_review_amount CHECK (amount_pesewas > 0),
    CONSTRAINT ck_disbursement_review_status
        CHECK (status IN ('pending', 'approved', 'rejected'))
);

UPDATE public.alembic_version
SET version_num = '0046_disbursement_reviews'
WHERE version_num = '0045_accounting_periods';

COMMIT;

SELECT version_num,
       to_regclass('public.loan_disbursement_reviews') IS NOT NULL AS reviews_ready,
       EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'public'
             AND table_name = 'finance_institutions'
             AND column_name = 'require_disbursement_approval'
       ) AS approval_column_ready
FROM public.alembic_version;
