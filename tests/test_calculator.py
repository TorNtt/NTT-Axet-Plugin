import math
from datetime import date

import pytest

from loan_calc.calculator import (
    amortisation_schedule,
    compare_offers,
    eligible_amount,
    emi,
    format_inr,
    outstanding_after,
    prepayment_savings,
    remaining_tenure,
    summary,
    total_interest,
    total_payment,
)


def test_emi_example_matches_expected_reference():
    # Acceptance criteria: EMI for ₹10,00,000 at 9% p.a. over 240 months ≈ ₹8,997 (±1)
    assert emi(1_000_000, 9.0, 240) == pytest.approx(8997, abs=1)


def test_emi_matches_unrounded_rate_reference_close():
    # Detect drift caused by rounding the monthly rate too aggressively.
    p, annual, n = 1_000_000, 9.0, 240
    r = annual / 1200.0  # unrounded monthly rate
    f = (1 + r) ** n
    ref = round(p * r * f / (f - 1), 2)
    assert emi(p, annual, n) == pytest.approx(ref, abs=0.05)


@pytest.mark.parametrize(
    "principal,annual_rate,tenure_months,expected",
    [
        (120_000, 0.0, 12, 10_000.00),
        (100_000, 0.0, 1, 100_000.00),
    ],
)
def test_emi_zero_interest(principal, annual_rate, tenure_months, expected):
    assert emi(principal, annual_rate, tenure_months) == expected


def test_emi_rejects_non_positive_inputs():
    with pytest.raises(ValueError):
        emi(0, 9.0, 12)
    with pytest.raises(ValueError):
        emi(100_000, 9.0, 0)


def test_total_payment_and_interest_consistency():
    p, r, n = 100_000, 12.0, 12
    tp = total_payment(p, r, n)
    ti = total_interest(p, r, n)
    assert tp == pytest.approx(emi(p, r, n) * n, abs=0.01)
    assert ti == pytest.approx(tp - p, abs=0.01)


def test_amortisation_schedule_length_and_last_balance_zeroish():
    p, r, n = 100_000, 12.0, 12
    sched = amortisation_schedule(p, r, n)
    assert len(sched) == n
    assert sched[-1]["balance"] == pytest.approx(0.0, abs=0.05)


def test_amortisation_schedule_principal_sums_to_original_principal():
    p, r, n = 250_000, 9.0, 240
    sched = amortisation_schedule(p, r, n)
    principal_paid = sum(row["principal"] for row in sched)
    assert principal_paid == pytest.approx(p, abs=1.0)


def test_outstanding_after_months_paid_edges():
    p, r, n = 100_000, 12.0, 12
    assert outstanding_after(p, r, n, 0) == pytest.approx(p, abs=0.01)

    sched = amortisation_schedule(p, r, n)
    assert outstanding_after(p, r, n, 1) == pytest.approx(sched[0]["balance"], abs=0.01)

    assert outstanding_after(p, r, n, n + 10) == 0.0


def test_remaining_tenure_zero_rate_is_simple_division():
    assert remaining_tenure(100_000, 0.0, 10_000) == 10
    assert remaining_tenure(1, 0.0, 10_000) == 1


def test_remaining_tenure_rejects_too_small_emi():
    # With positive rate, EMI must exceed interest-only payment.
    with pytest.raises(ValueError):
        remaining_tenure(100_000, 12.0, 1)


def test_remaining_tenure_matches_simulation_monthly_rate():
    # remaining_tenure should use monthly rate = annual_rate/1200, not annual_rate/100.
    balance = 100_000.0
    annual_rate = 12.0
    instalment = 9_000.0
    r = annual_rate / 1200.0

    # Simulate month-by-month payoff (interest then principal).
    months = 0
    b = balance
    while b > 0 and months < 10_000:
        interest = b * r
        principal_paid = instalment - interest
        if principal_paid <= 0:
            pytest.fail("simulation: instalment too small")
        b -= principal_paid
        months += 1

    # remaining_tenure uses ceil, so allow +/- 1 tolerance vs simulation.
    got = remaining_tenure(balance, annual_rate, instalment)
    assert got == pytest.approx(months, abs=1)


def test_prepayment_larger_than_balance_closes_loan():
    p, r, n = 200_000, 10.0, 24
    sched = amortisation_schedule(p, r, n)
    bal_after_6 = sched[5]["balance"]

    res = prepayment_savings(p, r, n, prepay_month=6, prepay_amount=bal_after_6 + 1)
    assert res["new_tenure"] == pytest.approx(6.0, abs=0.001)
    assert res["months_saved"] == pytest.approx(n - 6, abs=0.001)
    assert res["interest_saved"] >= 0


def test_compare_offers_sorts_by_total_cost():
    p = 500_000
    offers = [
        {"bank": "A", "rate": 10.0, "tenure": 120, "processing_fee_pct": 1.0},
        {"bank": "B", "rate": 9.0, "tenure": 120, "processing_fee_pct": 1.0},
        {"bank": "C", "rate": 9.0, "tenure": 120, "processing_fee_pct": 2.0},
    ]
    out = compare_offers(p, offers)

    # Sorted ascending by numeric total_cost
    costs = [x["total_cost"] for x in out]
    assert costs == sorted(costs)

    # Among these offers, B should be cheapest (lower rate than A, and lower fee than C).
    assert out[0]["bank"] == "B"


def test_eligible_amount_zero_interest_is_linear():
    # available EMI = 50_000 * 0.5 - 0 = 25_000; tenure=12 => principal=300_000
    assert eligible_amount(50_000, 0, 0.0, 12, foir=0.5) == 300_000.00


def test_format_inr_indian_grouping_and_sign():
    assert format_inr(1_000_000) == "₹10,00,000.00"
    assert format_inr(-1_000_000) == "-₹10,00,000.00"
    assert format_inr(1234.5) == "₹1,234.50"


def test_summary_contains_expected_fields_and_last_emi():
    s = summary(100_000, 9.0, 14, start=date(2020, 1, 10))
    assert set(s.keys()) == {
        "principal",
        "rate",
        "tenure",
        "emi",
        "total_interest",
        "total_payment",
        "last_emi",
        "currency",
    }
    # Jan 2020 + 14 months => Mar 2021
    assert s["last_emi"] == "2021-03"
