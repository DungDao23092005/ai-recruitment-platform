# Operational recovery scripts

This folder holds one-off, human-approved database recovery scripts for
entitlement incidents that the application cannot safely self-heal.

These scripts are **not** migrations and **not** application code. They are
reviewed, executed, and verified by a human operator (DBA/engineer) against a
specific, audited incident. Incident-specific identifiers (order ids,
subscription ids, provider references, amounts) live **inside each script's
Section 0**, never in this runbook or in general application code.

## When a script here is needed

A payment is captured by the provider (`payment_orders.status = 'paid'`,
`payment_transactions.status = 'success'`) but the bound subscription was never
activated and is still `pending`, while an older subscription remains
`active`. This is an *entitlement incident*: money was taken but no
entitlement was granted.

## Non-negotiable rules

1. **Never run the script as a whole on first contact.** Set the script's
   `@ConfirmRecovery` flag to `0` (its default) so it executes as a read-only
   dry run.
2. **Compare every read-only result to the audit/plan.** The incident
   identifiers and the expected values must already be documented and
   cross-checked by the audit phase. If reality differs, stop.
3. **Never edit a script to make it "pass".** A precondition failure is a
   signal to investigate, not to relax the guard.
4. **One atomic transaction.** All data changes commit or roll back together.
   Do not run the mutations outside the script's `TRY`/`CATCH`.
5. **No external calls under lock.** The scripts never touch the payment
   provider; they only reconcile data already persisted.
6. **Take a backup / know your restore point** before enabling recovery.

## Pre-execution checklist

- [ ] The incident has an approved audit/plan (identifiers, expected values,
      and the exact target database are documented).
- [ ] You are connected to the **correct server and database** (check
      `DB_NAME()`, `@@SERVERNAME`, `SUSER_SNAME()` printed by the script).
- [ ] You have a verified backup or a known-good restore point.
- [ ] You are running during an agreed maintenance window.
- [ ] `@ConfirmRecovery` is still `0`.

## Execution procedure

1. Open the incident script and run **Section 1 (read-only)** only.
   Confirm the user, payment order, payment transaction, target subscription,
   superseded subscription, and plans match the audit exactly.
2. Confirm the incident scan returns exactly the target case and nothing else.
3. Set `@ConfirmRecovery = 1` and (optionally) fill the pin variables
   (`@ExpectedUserId`, `@Expected*PlanId`, `@ExpectedDatabaseName`) from the
   audit so the script can cross-check the derived values.
4. Run **Section 2**. The script locks `User -> PaymentOrder -> Subscription`,
   re-validates every precondition under lock, and aborts (rolling back) on any
   mismatch.
5. Record the outcome row (`outcome`, `confirm_recovery_flag`).

## Expected outcomes

| `outcome` | Meaning |
|---|---|
| `RECOVERY COMMITTED - ...` | Preconditions passed and the recovery was applied. |
| `ALREADY CONSISTENT - ...` | The data already matches the recovered state; nothing changed. |
| `RECOVERY ABORTED - transaction rolled back` (+ error) | A precondition/postcondition failed; no partial change occurred. |

## Post-verification (after an approved execution)

- Exactly one non-deleted `active` subscription remains for the user.
- The target subscription has the correct plan, `started_at` (= audited
  `paid_at`), `expires_at` (= `paid_at` + plan `duration_days`) and quota
  snapshot read from the plan.
- The superseded subscription is `cancelled` with its usage counters unchanged.
- No `paid` order remains linked to a `pending` subscription for the user.
- The original `payment_orders` / `payment_transactions` rows are unchanged.

## Adding a new incident script

Copy the structure of an existing incident script and replace **only** Section 0
(identifiers and expected values). Keep the read-only section, the
`@ConfirmRecovery` guard, the lock ordering, the fail-closed preconditions, the
row-count checks, the postconditions and the `TRY`/`CATCH` rollback intact.
