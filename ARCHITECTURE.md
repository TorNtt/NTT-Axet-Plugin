# loan-calc architecture (legacy module notes)

This repository is a small, single-module Python library that computes common loan metrics:

- EMI (equal monthly instalment)
- Total payment / total interest
- Amortisation schedule (month-by-month split of EMI into interest and principal)
- Outstanding balance after N payments
- Remaining tenure given a balance and EMI
- Prepayment savings (keep EMI same, reduce tenure)
- Offer comparison and eligibility estimation
- Formatting helpers + CSV export
- A summary helper that produces display-ready strings

The implementation is mainly in `loan_calc/calculator.py`, with the functions operating on plain numbers (floats/ints) and returning either floats or simple dict/list structures.

## Module: `loan_calc/calculator.py`

### Constants
- `DEFAULT_CURRENCY = \"INR\"`: used by `summary()`.

### Internal helper
- `_monthly_rate(annual_rate)`
  - Purpose: convert annual percentage rate (APR) into a monthly decimal rate.
  - Expected formula: `annual_rate / 1200` (e.g. 9% p.a. → 0.0075 per month).
  - Note: the legacy code rounds the monthly rate to 4 decimals, which can materially affect EMI and schedule accuracy for long tenures. Tests will confirm if this is one of the reported “wrong numbers”.

### Public API functions

- `emi(principal, annual_rate, tenure_months)`
  - Computes the monthly instalment for a fixed-rate amortising loan.
  - Validates: `principal > 0` and `tenure_months > 0`.
  - For 0% interest (monthly rate == 0): returns `principal / tenure_months`.
  - Otherwise uses the standard EMI formula:
    - Let `r` be monthly rate in decimal and `n` be tenure in months.
    - `f = (1 + r) ** n`
    - `emi = principal * r * f / (f - 1)`
  - Returns a value rounded to 2 decimals.

- `total_payment(principal, annual_rate, tenure_months)`
  - Computes total paid across the full tenure as `emi(...) * tenure_months`.
  - Rounded to 2 decimals.

- `total_interest(principal, annual_rate, tenure_months)`
  - Computes total interest as `total_payment - principal`.
  - Rounded to 2 decimals.

- `amortisation_schedule(principal, annual_rate, tenure_months)`
  - Builds a list of rows, each row being a dict:
    - `month`, `emi`, `interest`, `principal`, `balance`
  - It uses the EMI computed by `emi()` and iteratively reduces the balance.
  - **Important:** The schedule is expected to have exactly `tenure_months` rows (one per month). The current code iterates `for month in range(1, tenure_months)` which would only create `tenure_months - 1` rows, suggesting an off-by-one bug. Also there is a conditional `if month == tenure_months:` inside the loop which will never be true with the current range.

- `outstanding_after(principal, annual_rate, tenure_months, months_paid)`
  - Returns outstanding balance after `months_paid` payments.
  - If `months_paid <= 0`: returns the original principal.
  - Otherwise: builds the amortisation schedule and returns the balance from the corresponding row.
  - If `months_paid` exceeds the schedule length: returns 0.0.

- `remaining_tenure(balance, annual_rate, instalment)`
  - Computes how many months are needed to pay off `balance` if the EMI (`instalment`) is kept constant at a given annual rate.
  - Uses a log-based formula.
  - **Potential issue to verify in tests:** it sets `r = annual_rate / 100` which looks like an annual *decimal* rate, not a monthly rate; the usual formula should use monthly rate `annual_rate / 1200`.

- `prepayment_savings(principal, annual_rate, tenure_months, prepay_month, prepay_amount)`
  - Scenario: borrower prepays a lump sum at month `prepay_month` and continues paying the same EMI; tenure becomes shorter.
  - Steps:
    1. Compute the original EMI.
    2. Generate original amortisation schedule.
    3. Take balance at `prepay_month` and subtract `prepay_amount`.
    4. If new balance ≤ 0: loan closes (months_left = 0); else compute remaining months using `remaining_tenure`.
    5. Compute interest already paid before prepayment (sum of interest in schedule rows up to prepay month).
    6. Compute “new total paid” = EMI paid until prepay month + prepayment amount + EMI for remaining months.
    7. New interest = new_total - original principal.
    8. Interest saved = original_interest - new_interest.
  - Returns a dict with `emi`, `months_saved`, `new_tenure`, `interest_saved`, `interest_paid_before_prepayment`.
  - Edge cases to test:
    - `prepay_amount` >= outstanding balance (should close loan and months_left=0).
    - `prepay_month` at 1 or at last month.

- `compare_offers(principal, offers)`
  - Input: list of offer dicts: `{bank, rate, tenure, processing_fee_pct?}`.
  - Output: list of computed metrics per offer, sorted by `total_cost` ascending.
  - `processing_fee` is computed as a percentage of principal; total_cost = total_interest + processing_fee.

- `eligible_amount(monthly_income, existing_emis, annual_rate, tenure_months, foir=0.5)`
  - Computes maximum eligible principal given:
    - FOIR (fixed obligation to income ratio) limit: borrower can spend `monthly_income * foir` on EMIs total.
    - Available EMI capacity: `available = monthly_income * foir - existing_emis`.
  - If available <= 0 → 0.
  - Otherwise inverts the EMI formula to solve for principal given EMI capacity.
  - Handles 0% interest as a simple multiplication.

- `format_inr(amount)`
  - Formats a number into an INR string like `₹10,00,000.00` using Indian digit grouping.
  - Preserves sign and always prints 2 decimals.

- `schedule_to_csv(rows, path)`
  - Writes schedule rows to a CSV file with a header.

- `summary(principal, annual_rate, tenure_months, start=None)`
  - Convenience wrapper for UI/CLI: returns formatted strings for principal, rate, tenure, EMI, total interest/payment, last EMI month (YYYY-MM), and currency.
  - Computes “last_emi” by adding `tenure_months` months to the start date (approximate month arithmetic; no day-of-month handling).

## Prompt log requirement (AI mistake correction)
During test-driven work, I will record at least one instance where an AI explanation above (or a proposed test) turned out wrong, and correct it in this document (append a short note at the end).\n
