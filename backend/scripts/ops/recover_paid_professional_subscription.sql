/* ============================================================================
 * INCIDENT-SPECIFIC PAID-SUBSCRIPTION RECOVERY  (VNPAY -> Professional)
 * ----------------------------------------------------------------------------
 * PURPOSE
 *   Recover a single, audited entitlement incident: a VNPAY payment succeeded
 *   (PaymentOrder.status = 'paid', PaymentTransaction.status = 'success') but
 *   the paid Professional subscription was never activated and is still
 *   'pending' while an older Basic subscription remains 'active'.
 *
 * WHAT THIS SCRIPT DOES (only when every precondition passes)
 *   1. Basic subscription  : 'active'    -> 'cancelled'  (usage preserved)
 *   2. Professional subscr.: 'pending'   -> 'active'      (started_at = paid_at)
 *   3. expires_at          : started_at + plan.duration_days
 *   4. quota snapshot      : read dynamically from recruitment_plans
 *   5. usage counters      : zeroed ONLY for a confirmed never-used pending sub
 *
 * WHAT THIS SCRIPT NEVER DOES
 *   - Never creates/updates/deletes any PaymentOrder or PaymentTransaction.
 *   - Never touches any other user, plan, or subscription.
 *   - Never performs a role transition or profile creation (application code
 *     owns that; this incident's user is already a recruiter because they hold
 *     an active Basic subscription).
 *
 * !!! DO NOT RUN THIS FILE DIRECTLY. !!!
 *   - Review the AGY Final Review and obtain an explicit human decision first.
 *   - Run SECTION 1 (read-only) alone, compare every row to the AGY Recovery
 *     Plan, and only then set @ConfirmRecovery = 1 and run SECTION 2.
 *   - @ConfirmRecovery defaults to 0: the script is then a pure read-only
 *     dry run and issues no data-modifying statement.
 *
 * LOCKING
 *   Follows the verified application hierarchy: User -> PaymentOrder ->
 *   Subscription. The user row is locked first, then the order, then the
 *   subscription rows, all inside ONE transaction. No external call is made.
 *
 * TARGET SCHEMA (verified from app/models + alembic revisions 47c75548f388,
 * sub_quota_enforcement)
 *   users(id UNIQUEIDENTIFIER, role VARCHAR(50), is_active BIT, is_deleted BIT)
 *   recruitment_plans(id, price INT, currency VARCHAR(10), duration_days INT,
 *                     max_job_posts INT NOT NULL, max_candidate_searches INT NULL,
 *                     max_ai_features INT NULL, is_active BIT, is_deleted BIT)
 *   subscriptions(id, user_id, plan_id, status VARCHAR(50),
 *                 started_at DATETIMEOFFSET NULL, expires_at DATETIMEOFFSET NULL,
 *                 max_job_posts/max_candidate_searches/max_ai_features INT NOT NULL,
 *                 job_posts_used/candidate_searches_used/ai_features_used INT NOT NULL,
 *                 updated_at DATETIMEOFFSET NOT NULL, is_deleted BIT)
 *   payment_orders(id, user_id, plan_id, subscription_id NULL, amount INT,
 *                  currency VARCHAR(10), provider VARCHAR(50),
 *                  internal_order_id VARCHAR(100), provider_order_id VARCHAR(100) NULL,
 *                  status VARCHAR(50), paid_at DATETIMEOFFSET NULL, is_deleted BIT)
 *   payment_transactions(id, payment_order_id, provider_transaction_id VARCHAR(100) NULL,
 *                        provider_result_code VARCHAR(50) NULL, status VARCHAR(50),
 *                        is_deleted BIT)
 *   subscription_usages(id, subscription_id, user_id, feature_type, status)
 *   Status values are lowercase: 'pending'/'paid'/'success'/'active'/'cancelled'.
 * ========================================================================= */

SET NOCOUNT ON;
SET XACT_ABORT ON;

/* ---------------------------------------------------------------------------
 * SECTION 0 - INCIDENT IDENTIFIERS
 *   Values below are the audited, immutable facts of THIS incident. Do not
 *   change them to "make the script pass"; if reality differs, STOP.
 * ------------------------------------------------------------------------- */
DECLARE @PaymentOrderId     UNIQUEIDENTIFIER = 'BACC1B65-1BFB-4D56-93AA-5DCCAE53A241';
DECLARE @ProfessionalSubId  UNIQUEIDENTIFIER = '636CC16B-5A05-4A4A-B093-FB047DDAB86F';
DECLARE @BasicSubId         UNIQUEIDENTIFIER = 'E2374F50-F6D4-4475-9812-7BA6A06ADB25';
DECLARE @ProviderTxnId      NVARCHAR(100)    = N'15707229';
DECLARE @ExpectedAmount     INT              = 299000;
DECLARE @ExpectedCurrency   NVARCHAR(10)     = N'VND';
DECLARE @ExpectedResultCode NVARCHAR(50)     = N'00';

/* Verified expected values from the AGY Recovery Plan. These are exact, not
 * optional: when set, the derived value must equal the pin or the script
 * aborts. A configured pin is never silently replaced by a derived value. */
DECLARE @ExpectedUserId             UNIQUEIDENTIFIER = '04E9EDF6-B1D6-4977-B8EC-376BC7D99DA2';
DECLARE @ExpectedProfessionalPlanId UNIQUEIDENTIFIER = '34D7DC19-B11D-4D18-9788-AA2236A2A449';
DECLARE @ExpectedBasicPlanId        UNIQUEIDENTIFIER = 'A703C988-C1B4-4F1F-9718-9485380D110E';
/* The original VNPAY merchant reference (payment_orders.internal_order_id). */
DECLARE @ExpectedInternalOrderRef   NVARCHAR(100)    = N'VNPAY_20261017_052825_B3FAF897';

/* Optional target-database pin. NULL -> not enforced (context is printed). */
DECLARE @ExpectedDatabaseName NVARCHAR(128) = NULL;

/* SAFETY SWITCH. 0 = read-only dry run (default). Set to 1 only for an
 * approved execution after reviewing SECTION 1 output.
 * Declared as INT (not BIT): BIT converts any non-zero assignment to 1, so an
 * accidental `SET @ConfirmRecovery = 2` would flip a BIT switch to 1 and open
 * the mutation branch. With INT, only the literal value 1 matches the gate;
 * 0, NULL, 2, -1 and every other integer stay on the read-only path. */
DECLARE @ConfirmRecovery INT = 0;

/* ---------------------------------------------------------------------------
 * SECTION 1 - READ-ONLY VERIFICATION
 *   These statements never modify data. Run this section first and confirm
 *   that the rows match the AGY Recovery Plan before enabling recovery.
 * ------------------------------------------------------------------------- */
PRINT '== Context ==================================================';
SELECT
    DB_NAME()                       AS current_database,
    @@SERVERNAME                    AS server_name,
    SUSER_SNAME()                   AS login_name,
    SYSDATETIMEOFFSET() AT TIME ZONE 'UTC' AS utc_now,
    @ConfirmRecovery                AS confirm_recovery_flag;

/* Resolve the identifiers the audited rows actually point at (read-only). */
DECLARE @UserId    UNIQUEIDENTIFIER;
DECLARE @ProPlanId UNIQUEIDENTIFIER;
SELECT @UserId = po.user_id, @ProPlanId = po.plan_id
FROM payment_orders po
WHERE po.id = @PaymentOrderId;

PRINT '== User =====================================================';
SELECT u.id, u.email, u.role, u.is_active, u.is_deleted
FROM users u
WHERE u.id = @UserId;

PRINT '== PaymentOrder (must remain unchanged) =====================';
SELECT po.id, po.user_id, po.plan_id, po.subscription_id, po.amount, po.currency,
       po.provider, po.internal_order_id, po.provider_order_id, po.provider_request_id,
       po.status, po.paid_at, po.expired_at, po.created_at, po.updated_at, po.is_deleted
FROM payment_orders po
WHERE po.id = @PaymentOrderId;

PRINT '== PaymentTransaction(s) for the order =======================';
SELECT pt.id, pt.payment_order_id, pt.provider_transaction_id, pt.provider_result_code,
       pt.provider_message, pt.status, pt.responded_at, pt.created_at, pt.updated_at,
       pt.is_deleted
FROM payment_transactions pt
WHERE pt.payment_order_id = @PaymentOrderId
ORDER BY pt.created_at;

PRINT '== Professional subscription (target) =======================';
SELECT s.id, s.user_id, s.plan_id, s.status, s.started_at, s.expires_at,
       s.max_job_posts, s.max_candidate_searches, s.max_ai_features,
       s.job_posts_used, s.candidate_searches_used, s.ai_features_used,
       s.created_at, s.updated_at, s.is_deleted
FROM subscriptions s
WHERE s.id = @ProfessionalSubId;

PRINT '== Basic subscription (to be retired) =======================';
SELECT s.id, s.user_id, s.plan_id, s.status, s.started_at, s.expires_at,
       s.max_job_posts, s.max_candidate_searches, s.max_ai_features,
       s.job_posts_used, s.candidate_searches_used, s.ai_features_used,
       s.created_at, s.updated_at, s.is_deleted
FROM subscriptions s
WHERE s.id = @BasicSubId;

PRINT '== Plans referenced ========================================';
SELECT rp.id, rp.name, rp.price, rp.currency, rp.duration_days,
       rp.max_job_posts, rp.max_candidate_searches, rp.max_ai_features,
       rp.is_active, rp.is_deleted
FROM recruitment_plans rp
WHERE rp.id IN (
    @ProPlanId,
    (SELECT s.plan_id FROM subscriptions s WHERE s.id = @BasicSubId)
);

PRINT '== All subscriptions of the user ===========================';
SELECT s.id, s.plan_id, rp.name AS plan_name, s.status, s.started_at, s.expires_at,
       s.is_deleted
FROM subscriptions s
LEFT JOIN recruitment_plans rp ON rp.id = s.plan_id
WHERE s.user_id = @UserId
ORDER BY s.created_at;

PRINT '== Incident scan: PAID orders whose bound subscription is PENDING ==';
SELECT po.id AS payment_order_id, po.internal_order_id, po.plan_id, po.amount,
       po.status AS order_status, po.paid_at, s.id AS subscription_id, s.status AS sub_status
FROM payment_orders po
JOIN subscriptions s ON s.id = po.subscription_id
WHERE po.user_id = @UserId
  AND po.is_deleted = 0
  AND po.status = 'paid'
  AND s.is_deleted = 0
  AND s.status = 'pending';

/* ---------------------------------------------------------------------------
 * SECTION 2 - RECOVERY (transactional, fail-closed)
 * ------------------------------------------------------------------------- */
/* EXECUTION GATE (fail-safe):
 *   Only the exact integer value 1 enters the mutation branch.
 *   `@ConfirmRecovery = 1` evaluates to UNKNOWN for NULL and FALSE for
 *   every other value, so NULL and any non-1 value fall through to the
 *   read-only ELSE (dry run). There is no control path that reaches the two
 *   UPDATE statements unless this predicate is exactly TRUE. */
IF @ConfirmRecovery = 1
BEGIN
    IF @ExpectedDatabaseName IS NOT NULL AND DB_NAME() <> @ExpectedDatabaseName
    BEGIN
        THROW 51000, N'Aborted: connected database is not the expected target database.', 1;
    END

    BEGIN TRY
        /* All state reads below are authoritative and re-validated under lock. */
        DECLARE @NowUtc DATETIMEOFFSET = SYSDATETIMEOFFSET() AT TIME ZONE 'UTC';
        DECLARE @RowCount INT;

        /* Locks/reads */
        DECLARE @UserIdLocked        UNIQUEIDENTIFIER;
        DECLARE @UserFound           BIT = 0;
        DECLARE @UserRole            NVARCHAR(50);
        DECLARE @UserDeleted         BIT;

        DECLARE @OrderFound          BIT = 0;
        DECLARE @OrderUserId         UNIQUEIDENTIFIER;
        DECLARE @OrderPlanId         UNIQUEIDENTIFIER;
        DECLARE @OrderSubscriptionId UNIQUEIDENTIFIER;
        DECLARE @OrderStatus         NVARCHAR(50);
        DECLARE @OrderProvider       NVARCHAR(50);
        DECLARE @OrderAmount         INT;
        DECLARE @OrderCurrency       NVARCHAR(10);
        DECLARE @OrderPaidAt         DATETIMEOFFSET;
        DECLARE @OrderProviderOrderId NVARCHAR(100);
        DECLARE @OrderInternalRef    NVARCHAR(100);
        DECLARE @OrderUpdatedAt      DATETIMEOFFSET;
        /* Post-mutation copies, used to prove the payment evidence is unchanged. */
        DECLARE @OrderStatusAfter    NVARCHAR(50);
        DECLARE @OrderPaidAtAfter    DATETIMEOFFSET;
        DECLARE @OrderProviderOrderIdAfter NVARCHAR(100);
        DECLARE @OrderInternalRefAfter NVARCHAR(100);
        DECLARE @OrderUpdatedAtAfter DATETIMEOFFSET;

        DECLARE @ProFound            BIT = 0;
        DECLARE @ProUserId           UNIQUEIDENTIFIER;
        DECLARE @ProSubPlanId        UNIQUEIDENTIFIER;
        DECLARE @ProStatus           NVARCHAR(50);
        DECLARE @ProStartedAt        DATETIMEOFFSET;
        DECLARE @ProExpiresAt        DATETIMEOFFSET;
        DECLARE @ProMaxJob           INT;
        DECLARE @ProMaxCand          INT;
        DECLARE @ProMaxAi            INT;
        DECLARE @ProJobUsed          INT;
        DECLARE @ProCandUsed         INT;
        DECLARE @ProAiUsed           INT;

        DECLARE @BasicFound          BIT = 0;
        DECLARE @BasicUserId         UNIQUEIDENTIFIER;
        DECLARE @BasicSubPlanId      UNIQUEIDENTIFIER;
        DECLARE @BasicStatus         NVARCHAR(50);
        DECLARE @BasicJobUsed        INT;
        DECLARE @BasicCandUsed       INT;
        DECLARE @BasicAiUsed         INT;
        /* Baseline captured at lock time; must be identical after recovery. */
        DECLARE @BasicStatusBefore   NVARCHAR(50);
        DECLARE @BasicJobUsedBefore  INT;
        DECLARE @BasicCandUsedBefore INT;
        DECLARE @BasicAiUsedBefore   INT;

        DECLARE @ProPlanFound        BIT = 0;
        DECLARE @ProPlanActive       BIT;
        DECLARE @ProPlanDuration     INT;
        DECLARE @ProPlanPrice        INT;
        DECLARE @ProPlanCurrency     NVARCHAR(10);
        DECLARE @ProPlanMaxJob       INT;
        DECLARE @ProPlanMaxCand      INT;
        DECLARE @ProPlanMaxAi        INT;

        DECLARE @BasicPlanFound      BIT = 0;
        DECLARE @BasicPlanActive     BIT;
        DECLARE @BasicPlanPrice      INT;
        DECLARE @BasicPlanCurrency   NVARCHAR(10);

        DECLARE @TxMatchCount        INT;
        DECLARE @TxConflictCount     INT;
        DECLARE @UsageCount          INT;
        DECLARE @ActiveCount         INT;
        DECLARE @OtherPaidOrders     INT;
        DECLARE @OtherOrdersForProSub INT;
        DECLARE @OtherPendingProSubs INT;
        DECLARE @RemainingPaidPending INT;

        DECLARE @PaidAtUtc           DATETIMEOFFSET;
        DECLARE @ExpectedExpiry      DATETIMEOFFSET;
        DECLARE @Outcome             NVARCHAR(200);

        BEGIN TRANSACTION;

        /* ---- Step 1: resolve owning user (unlocked read for the lock key) -- */
        SELECT @UserId = po.user_id
        FROM payment_orders po
        WHERE po.id = @PaymentOrderId;

        IF @UserId IS NULL
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder not found; cannot resolve owning user.', 1;
        END

        IF @ExpectedUserId IS NOT NULL AND @UserId <> @ExpectedUserId
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder user does not match the audited expected user.', 1;
        END

        /* ---- Step 2: lock User FIRST (hierarchy: User -> Order -> Subs) --- */
        SELECT @UserIdLocked = u.id, @UserFound = 1, @UserRole = u.role, @UserDeleted = u.is_deleted
        FROM users u WITH (UPDLOCK, ROWLOCK)
        WHERE u.id = @UserId;

        IF @UserFound = 0 OR @UserIdLocked IS NULL
        BEGIN
            THROW 51000, N'Aborted: user does not exist.', 1;
        END
        IF @UserDeleted = 1
        BEGIN
            THROW 51000, N'Aborted: user is soft-deleted.', 1;
        END
        IF @UserRole IS NULL OR @UserRole <> 'recruiter'
        BEGIN
            THROW 51000, N'Aborted: user is not a recruiter; this incident requires the application activation path (role transition/profile), not this script.', 1;
        END

        /* ---- Step 3: lock PaymentOrder ---- */
        SELECT @OrderFound = 1,
               @OrderUserId = po.user_id, @OrderPlanId = po.plan_id,
               @OrderSubscriptionId = po.subscription_id,
               @OrderStatus = po.status, @OrderProvider = po.provider,
               @OrderAmount = po.amount, @OrderCurrency = po.currency,
               @OrderPaidAt = po.paid_at, @OrderProviderOrderId = po.provider_order_id,
               @OrderInternalRef = po.internal_order_id, @OrderUpdatedAt = po.updated_at
        FROM payment_orders po WITH (UPDLOCK, ROWLOCK)
        WHERE po.id = @PaymentOrderId AND po.is_deleted = 0;

        IF @OrderFound = 0
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder not found or soft-deleted.', 1;
        END
        IF @OrderUserId <> @UserId
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder user mismatch.', 1;
        END
        IF @OrderSubscriptionId IS NULL OR @OrderSubscriptionId <> @ProfessionalSubId
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder is not bound to the audited Professional subscription.', 1;
        END
        IF @OrderProvider <> 'vnpay'
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder provider is not VNPAY.', 1;
        END
        IF @OrderStatus <> 'paid'
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder is not in status paid.', 1;
        END
        IF @OrderAmount IS NULL OR @OrderAmount <> @ExpectedAmount
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder amount does not match the audited amount.', 1;
        END
        IF @OrderCurrency IS NULL OR @OrderCurrency <> @ExpectedCurrency
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder currency does not match the audited currency.', 1;
        END
        IF @OrderPaidAt IS NULL
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder paid_at is NULL; there is no valid paid timestamp to start from.', 1;
        END
        IF @OrderProviderOrderId IS NULL OR @OrderProviderOrderId <> @ProviderTxnId
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder provider_order_id does not match the audited provider transaction id.', 1;
        END
        IF @OrderInternalRef IS NULL
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder has no original order reference (internal_order_id).', 1;
        END
        IF @ExpectedInternalOrderRef IS NOT NULL AND @OrderInternalRef <> @ExpectedInternalOrderRef
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder original order reference does not match the audited reference.', 1;
        END
        IF @OrderPlanId <> @ProPlanId
        BEGIN
            THROW 51000, N'Aborted: PaymentOrder plan is inconsistent with resolved plan id.', 1;
        END
        IF @ExpectedProfessionalPlanId IS NOT NULL AND @ProPlanId <> @ExpectedProfessionalPlanId
        BEGIN
            THROW 51000, N'Aborted: Professional plan id does not match the audited expected plan.', 1;
        END

        SET @PaidAtUtc = @OrderPaidAt AT TIME ZONE 'UTC';

        /* ---- Step 3b: verify the success PaymentTransaction ---- */
        SELECT @TxMatchCount = COUNT(*)
        FROM payment_transactions pt
        WHERE pt.payment_order_id = @PaymentOrderId
          AND pt.is_deleted = 0
          AND pt.status = 'success'
          AND pt.provider_transaction_id = @ProviderTxnId
          AND pt.provider_result_code = @ExpectedResultCode;

        IF @TxMatchCount < 1
        BEGIN
            THROW 51000, N'Aborted: no successful PaymentTransaction matches the audited provider transaction id/result code.', 1;
        END

        SELECT @TxConflictCount = COUNT(*)
        FROM payment_transactions pt
        WHERE pt.payment_order_id = @PaymentOrderId
          AND pt.is_deleted = 0
          AND pt.status = 'success'
          AND (pt.provider_transaction_id IS NULL OR pt.provider_transaction_id <> @ProviderTxnId);

        IF @TxConflictCount > 0
        BEGIN
            THROW 51000, N'Aborted: a conflicting successful PaymentTransaction exists for this order.', 1;
        END

        /* ---- Step 4: lock Professional subscription ---- */
        SELECT @ProFound = 1,
               @ProUserId = s.user_id, @ProSubPlanId = s.plan_id, @ProStatus = s.status,
               @ProStartedAt = s.started_at, @ProExpiresAt = s.expires_at,
               @ProMaxJob = s.max_job_posts, @ProMaxCand = s.max_candidate_searches,
               @ProMaxAi = s.max_ai_features,
               @ProJobUsed = s.job_posts_used, @ProCandUsed = s.candidate_searches_used,
               @ProAiUsed = s.ai_features_used
        FROM subscriptions s WITH (UPDLOCK, ROWLOCK)
        WHERE s.id = @ProfessionalSubId AND s.is_deleted = 0;

        IF @ProFound = 0
        BEGIN
            THROW 51000, N'Aborted: Professional subscription not found or soft-deleted.', 1;
        END
        IF @ProUserId <> @UserId
        BEGIN
            THROW 51000, N'Aborted: Professional subscription user mismatch.', 1;
        END
        IF @ProSubPlanId IS NULL OR @ProSubPlanId <> @ProPlanId
        BEGIN
            THROW 51000, N'Aborted: Professional subscription plan mismatch.', 1;
        END
        IF @ProStatus NOT IN ('pending', 'active')
        BEGIN
            THROW 51000, N'Aborted: Professional subscription is not in a recoverable state (pending) nor already active.', 1;
        END

        /* ---- Step 5: lock Basic subscription ---- */
        SELECT @BasicFound = 1,
               @BasicUserId = s.user_id, @BasicSubPlanId = s.plan_id,
               @BasicStatusBefore = s.status,
               @BasicJobUsedBefore = s.job_posts_used,
               @BasicCandUsedBefore = s.candidate_searches_used,
               @BasicAiUsedBefore = s.ai_features_used
        FROM subscriptions s WITH (UPDLOCK, ROWLOCK)
        WHERE s.id = @BasicSubId AND s.is_deleted = 0;

        IF @BasicFound = 0
        BEGIN
            THROW 51000, N'Aborted: Basic subscription not found or soft-deleted.', 1;
        END
        IF @BasicUserId <> @UserId
        BEGIN
            THROW 51000, N'Aborted: Basic subscription user mismatch.', 1;
        END
        IF @BasicSubPlanId IS NULL OR @BasicSubPlanId = @ProPlanId
        BEGIN
            THROW 51000, N'Aborted: Basic subscription does not reference a distinct plan.', 1;
        END
        IF @ExpectedBasicPlanId IS NOT NULL AND @BasicSubPlanId <> @ExpectedBasicPlanId
        BEGIN
            THROW 51000, N'Aborted: Basic plan id does not match the audited expected plan.', 1;
        END

        /* ---- Step 6: read plans (authoritative quota/duration source) ---- */
        SELECT @ProPlanFound = 1,
               @ProPlanActive = rp.is_active, @ProPlanDuration = rp.duration_days,
               @ProPlanPrice = rp.price, @ProPlanCurrency = rp.currency,
               @ProPlanMaxJob = rp.max_job_posts, @ProPlanMaxCand = rp.max_candidate_searches,
               @ProPlanMaxAi = rp.max_ai_features
        FROM recruitment_plans rp
        WHERE rp.id = @ProPlanId AND rp.is_deleted = 0;

        IF @ProPlanFound = 0
        BEGIN
            THROW 51000, N'Aborted: Professional plan not found or soft-deleted.', 1;
        END
        IF @ProPlanActive IS NULL OR @ProPlanActive <> 1
        BEGIN
            THROW 51000, N'Aborted: Professional plan is not active.', 1;
        END
        IF @ProPlanDuration IS NULL OR @ProPlanDuration <= 0
        BEGIN
            THROW 51000, N'Aborted: Professional plan duration_days is not positive.', 1;
        END
        IF @ProPlanPrice IS NULL OR @ProPlanPrice <> @ExpectedAmount
        BEGIN
            THROW 51000, N'Aborted: Professional plan price does not match the audited paid amount.', 1;
        END
        IF @ProPlanCurrency IS NULL OR @ProPlanCurrency <> @ExpectedCurrency
        BEGIN
            THROW 51000, N'Aborted: Professional plan currency does not match the audited currency.', 1;
        END
        /* Every Professional quota must be present and non-negative. A missing
         * (NULL) quota is a data defect and must abort rather than be silently
         * coerced to 0 in the UPDATE. */
        IF @ProPlanMaxJob IS NULL OR @ProPlanMaxJob < 0
        BEGIN
            THROW 51000, N'Aborted: Professional plan max_job_posts is NULL or negative.', 1;
        END
        IF @ProPlanMaxCand IS NULL OR @ProPlanMaxCand < 0
        BEGIN
            THROW 51000, N'Aborted: Professional plan max_candidate_searches is NULL or negative.', 1;
        END
        IF @ProPlanMaxAi IS NULL OR @ProPlanMaxAi < 0
        BEGIN
            THROW 51000, N'Aborted: Professional plan max_ai_features is NULL or negative.', 1;
        END

        SELECT @BasicPlanFound = 1,
               @BasicPlanActive = rp.is_active, @BasicPlanPrice = rp.price,
               @BasicPlanCurrency = rp.currency
        FROM recruitment_plans rp
        WHERE rp.id = @BasicSubPlanId AND rp.is_deleted = 0;

        IF @BasicPlanFound = 0
        BEGIN
            THROW 51000, N'Aborted: Basic plan not found or soft-deleted.', 1;
        END

        SET @ExpectedExpiry = DATEADD(DAY, @ProPlanDuration, @PaidAtUtc);

        /* ---- Step 7: conflict / uniqueness guards ---- */
        SELECT @ActiveCount = COUNT(*)
        FROM subscriptions s
        WHERE s.user_id = @UserId AND s.is_deleted = 0
          AND s.status = 'active';

        IF @ActiveCount <> 1
        BEGIN
            THROW 51000, N'Aborted: expected exactly one active subscription for the user before recovery.', 1;
        END

        SELECT @OtherPaidOrders = COUNT(*)
        FROM payment_orders po
        WHERE po.user_id = @UserId AND po.plan_id = @ProPlanId AND po.is_deleted = 0
          AND po.status = 'paid' AND po.id <> @PaymentOrderId;

        IF @OtherPaidOrders > 0
        BEGIN
            THROW 51000, N'Aborted: another paid order exists for the same user and Professional plan; recovery assumptions are invalidated.', 1;
        END

        SELECT @OtherOrdersForProSub = COUNT(*)
        FROM payment_orders po
        WHERE po.subscription_id = @ProfessionalSubId AND po.is_deleted = 0
          AND po.id <> @PaymentOrderId;

        IF @OtherOrdersForProSub > 0
        BEGIN
            THROW 51000, N'Aborted: another PaymentOrder references the Professional subscription.', 1;
        END

        SELECT @OtherPendingProSubs = COUNT(*)
        FROM subscriptions s
        WHERE s.user_id = @UserId AND s.plan_id = @ProPlanId AND s.is_deleted = 0
          AND s.status = 'pending' AND s.id <> @ProfessionalSubId;

        IF @OtherPendingProSubs > 0
        BEGIN
            THROW 51000, N'Aborted: another pending subscription exists for the same user and Professional plan.', 1;
        END

        /* ===================================================================
         * BRANCH A - already recovered: verify full consistency, change nothing
         * =================================================================== */
        IF @ProStatus = 'active'
        BEGIN
            IF @BasicStatusBefore <> 'cancelled'
            BEGIN
                THROW 51000, N'Aborted: Professional is active but the Basic subscription is not cancelled; refusing to overwrite inconsistent data.', 1;
            END
            IF @ProStartedAt IS NULL OR @ProStartedAt <> @PaidAtUtc
            BEGIN
                THROW 51000, N'Aborted: already-active Professional started_at does not match the audited paid_at.', 1;
            END
            IF @ProExpiresAt IS NULL OR @ProExpiresAt <> @ExpectedExpiry
            BEGIN
                THROW 51000, N'Aborted: already-active Professional expires_at does not match paid_at + plan duration.', 1;
            END
            IF @ProMaxJob <> @ProPlanMaxJob
               OR @ProMaxCand <> @ProPlanMaxCand
               OR @ProMaxAi <> @ProPlanMaxAi
            BEGIN
                THROW 51000, N'Aborted: already-active Professional quota snapshot does not match the plan.', 1;
            END
            IF @ProJobUsed IS NULL OR @ProCandUsed IS NULL OR @ProAiUsed IS NULL
               OR @ProJobUsed < 0 OR @ProCandUsed < 0 OR @ProAiUsed < 0
               OR @BasicJobUsedBefore < 0 OR @BasicCandUsedBefore < 0 OR @BasicAiUsedBefore < 0
            BEGIN
                THROW 51000, N'Aborted: usage counters are NULL or negative.', 1;
            END

            SET @Outcome = N'ALREADY CONSISTENT - recovery previously completed; no changes made.';
        END
        /* ===================================================================
         * BRANCH B - pending: perform the recovery mutations
         * =================================================================== */
        ELSE /* @ProStatus = 'pending' */
        BEGIN
            IF @BasicStatusBefore <> 'active'
            BEGIN
                THROW 51000, N'Aborted: Basic subscription is not active; cannot determine the superseded entitlement.', 1;
            END
            IF @BasicPlanCurrency IS NULL OR @ProPlanCurrency IS NULL
               OR @BasicPlanCurrency <> @ProPlanCurrency
            BEGIN
                THROW 51000, N'Aborted: Basic and Professional plans are not in the same currency.', 1;
            END
            IF @BasicPlanPrice IS NULL OR @BasicPlanPrice >= @ProPlanPrice
            BEGIN
                THROW 51000, N'Aborted: Professional is not a strictly higher-priced upgrade over Basic.', 1;
            END

            /* Confirm the target is a never-used pending subscription before
             * zeroing its usage counters. */
            IF @ProJobUsed <> 0 OR @ProCandUsed <> 0 OR @ProAiUsed <> 0
            BEGIN
                THROW 51000, N'Aborted: pending Professional subscription has non-zero usage counters; refusing to reset them.', 1;
            END

            SELECT @UsageCount = COUNT(*)
            FROM subscription_usages su
            WHERE su.subscription_id = @ProfessionalSubId;

            IF @UsageCount <> 0
            BEGIN
                THROW 51000, N'Aborted: pending Professional subscription already has usage records; refusing to reset counters.', 1;
            END

            /* Mutation 1: retire the superseded Basic subscription. Usage
             * counters and quota snapshot are preserved as historical record. */
            UPDATE subscriptions
            SET status = 'cancelled',
                updated_at = @NowUtc
            WHERE id = @BasicSubId AND status = 'active' AND is_deleted = 0;

            SET @RowCount = @@ROWCOUNT;
            IF @RowCount <> 1
            BEGIN
                THROW 51000, N'Aborted: Basic subscription was not cancelled exactly once.', 1;
            END

            /* Mutation 2: activate the paid Professional subscription, using
             * the audited paid_at as started_at, with a fresh quota snapshot
             * read from the plan and zeroed usage counters. */
            UPDATE subscriptions
            SET status = 'active',
                started_at = @PaidAtUtc,
                expires_at = @ExpectedExpiry,
                max_job_posts = @ProPlanMaxJob,
                max_candidate_searches = @ProPlanMaxCand,
                max_ai_features = @ProPlanMaxAi,
                job_posts_used = 0,
                candidate_searches_used = 0,
                ai_features_used = 0,
                updated_at = @NowUtc
            WHERE id = @ProfessionalSubId AND status = 'pending' AND is_deleted = 0;

            SET @RowCount = @@ROWCOUNT;
            IF @RowCount <> 1
            BEGIN
                THROW 51000, N'Aborted: Professional subscription was not activated exactly once.', 1;
            END

            SET @Outcome = N'RECOVERY COMMITTED - Basic retired, Professional activated.';
        END

        /* ===================================================================
         * POSTCONDITIONS - a failure here rolls back the whole transaction
         * =================================================================== */

        SELECT @ActiveCount = COUNT(*)
        FROM subscriptions s
        WHERE s.user_id = @UserId AND s.is_deleted = 0
          AND s.status = 'active';
        IF @ActiveCount <> 1
        BEGIN
            THROW 51000, N'Postcondition failed: expected exactly one active subscription for the user.', 1;
        END

        SELECT @ProStatus = s.status, @ProStartedAt = s.started_at, @ProExpiresAt = s.expires_at,
               @ProMaxJob = s.max_job_posts, @ProMaxCand = s.max_candidate_searches,
               @ProMaxAi = s.max_ai_features
        FROM subscriptions s
        WHERE s.id = @ProfessionalSubId;
        IF @ProStatus <> 'active'
           OR @ProStartedAt <> @PaidAtUtc
           OR @ProExpiresAt <> @ExpectedExpiry
           OR @ProMaxJob <> @ProPlanMaxJob
           OR @ProMaxCand <> @ProPlanMaxCand
           OR @ProMaxAi <> @ProPlanMaxAi
        BEGIN
            THROW 51000, N'Postcondition failed: Professional subscription state/quota is incorrect.', 1;
        END

        SELECT @BasicStatus = s.status,
               @BasicJobUsed = s.job_posts_used,
               @BasicCandUsed = s.candidate_searches_used,
               @BasicAiUsed = s.ai_features_used
        FROM subscriptions s
        WHERE s.id = @BasicSubId;
        IF @BasicStatus <> 'cancelled'
        BEGIN
            THROW 51000, N'Postcondition failed: Basic subscription is not cancelled.', 1;
        END
        IF @BasicJobUsed <> @BasicJobUsedBefore
           OR @BasicCandUsed <> @BasicCandUsedBefore
           OR @BasicAiUsed <> @BasicAiUsedBefore
        BEGIN
            THROW 51000, N'Postcondition failed: Basic subscription usage counters changed.', 1;
        END

        SELECT @RemainingPaidPending = COUNT(*)
        FROM payment_orders po
        JOIN subscriptions s ON s.id = po.subscription_id
        WHERE po.user_id = @UserId AND po.is_deleted = 0 AND po.status = 'paid'
          AND s.is_deleted = 0 AND s.status = 'pending';
        IF @RemainingPaidPending <> 0
        BEGIN
            THROW 51000, N'Postcondition failed: a paid order is still linked to a pending subscription.', 1;
        END

        /* Prove the original payment evidence was not modified: re-read the
         * order and compare every captured field to its locked pre-image. */
        SELECT @OrderStatusAfter = po.status, @OrderPaidAtAfter = po.paid_at,
               @OrderProviderOrderIdAfter = po.provider_order_id,
               @OrderInternalRefAfter = po.internal_order_id,
               @OrderUpdatedAtAfter = po.updated_at
        FROM payment_orders po
        WHERE po.id = @PaymentOrderId;
        IF @OrderStatusAfter <> @OrderStatus
           OR @OrderPaidAtAfter <> @OrderPaidAt
           OR @OrderProviderOrderIdAfter <> @OrderProviderOrderId
           OR @OrderInternalRefAfter <> @OrderInternalRef
           OR @OrderUpdatedAtAfter <> @OrderUpdatedAt
           OR @OrderStatusAfter <> 'paid'
           OR @OrderProviderOrderIdAfter <> @ProviderTxnId
        BEGIN
            THROW 51000, N'Postcondition failed: original PaymentOrder fields changed.', 1;
        END

        SELECT @TxMatchCount = COUNT(*)
        FROM payment_transactions pt
        WHERE pt.payment_order_id = @PaymentOrderId AND pt.is_deleted = 0
          AND pt.status = 'success' AND pt.provider_transaction_id = @ProviderTxnId
          AND pt.provider_result_code = @ExpectedResultCode;
        IF @TxMatchCount < 1
        BEGIN
            THROW 51000, N'Postcondition failed: original PaymentTransaction is no longer intact.', 1;
        END

        COMMIT TRANSACTION;
        SELECT @Outcome AS outcome, @ConfirmRecovery AS confirm_recovery_flag;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        SELECT N'RECOVERY ABORTED - transaction rolled back' AS outcome,
               ERROR_NUMBER()  AS error_number,
               ERROR_MESSAGE() AS error_message;
        THROW;
    END CATCH
END
ELSE
BEGIN
    /* Read-only dry run: reached for @ConfirmRecovery = 0, NULL, or any value
     * other than exactly 1. No DML exists on this path. */
    PRINT '============================================================';
    PRINT ' DRY RUN (@ConfirmRecovery is 0 or NULL). No data was modified.';
    PRINT ' Review SECTION 1 output against the AGY Recovery Plan, then';
    PRINT ' set @ConfirmRecovery = 1 and re-run to execute recovery.';
    PRINT '============================================================';
END
