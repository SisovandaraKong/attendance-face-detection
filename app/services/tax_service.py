"""Tax & social security calculation engine.

Cambodia-based tax brackets (simplified) and NSSF contributions.
Configurable via environment variables for different jurisdictions.
"""

from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP


# ── Tax brackets (monthly income in USD, Cambodia simplified) ──
# Bracket format: (upper_limit, rate)  — income up to upper_limit is taxed at rate
TAX_BRACKETS: list[tuple[Decimal, Decimal]] = [
    (Decimal("1500000"), Decimal("0.00")),     # 0%  on first 1,500,000 KHR (~$375)
    (Decimal("2000000"), Decimal("0.05")),     # 5%  on 1,500,001 – 2,000,000
    (Decimal("8500000"), Decimal("0.10")),     # 10% on 2,000,001 – 8,500,000
    (Decimal("12500000"), Decimal("0.15")),    # 15% on 8,500,001 – 12,500,000
    (Decimal("999999999"), Decimal("0.20")),   # 20% on above 12,500,000
]

# USD to KHR exchange rate for tax bracket conversion
KHR_RATE = Decimal(os.getenv("KHR_EXCHANGE_RATE", "4100"))

# NSSF (National Social Security Fund) contribution rates
NSSF_EMPLOYEE_RATE = Decimal(os.getenv("NSSF_EMPLOYEE_RATE", "0.02"))  # 2%
NSSF_EMPLOYER_RATE = Decimal(os.getenv("NSSF_EMPLOYER_RATE", "0.028"))  # 2.8%
NSSF_SALARY_CAP = Decimal(os.getenv("NSSF_SALARY_CAP", "1200000"))  # 1,200,000 KHR cap


def _money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_income_tax(monthly_salary_usd: Decimal) -> Decimal:
    """Calculate monthly income tax based on progressive brackets.

    Converts USD salary to KHR for bracket lookup, returns tax in USD.
    """
    salary_khr = _money(monthly_salary_usd * KHR_RATE)
    tax_khr = Decimal("0")
    previous_limit = Decimal("0")

    for upper_limit, rate in TAX_BRACKETS:
        if salary_khr <= previous_limit:
            break
        taxable = min(salary_khr, upper_limit) - previous_limit
        if taxable > 0:
            tax_khr += _money(taxable * rate)
        previous_limit = upper_limit

    # Convert back to USD
    if KHR_RATE > 0:
        return _money(tax_khr / KHR_RATE)
    return Decimal("0.00")


def calculate_nssf_employee(monthly_salary_usd: Decimal) -> Decimal:
    """Calculate employee's NSSF contribution."""
    salary_khr = _money(monthly_salary_usd * KHR_RATE)
    capped = min(salary_khr, NSSF_SALARY_CAP)
    contribution_khr = _money(capped * NSSF_EMPLOYEE_RATE)
    if KHR_RATE > 0:
        return _money(contribution_khr / KHR_RATE)
    return Decimal("0.00")


def calculate_nssf_employer(monthly_salary_usd: Decimal) -> Decimal:
    """Calculate employer's NSSF contribution."""
    salary_khr = _money(monthly_salary_usd * KHR_RATE)
    capped = min(salary_khr, NSSF_SALARY_CAP)
    contribution_khr = _money(capped * NSSF_EMPLOYER_RATE)
    if KHR_RATE > 0:
        return _money(contribution_khr / KHR_RATE)
    return Decimal("0.00")


def calculate_tax_breakdown(gross_salary_usd: Decimal) -> dict:
    """Return full tax breakdown for a given gross salary."""
    tax = calculate_income_tax(gross_salary_usd)
    nssf_ee = calculate_nssf_employee(gross_salary_usd)
    nssf_er = calculate_nssf_employer(gross_salary_usd)
    total_deductions = tax + nssf_ee
    net_after_tax = _money(gross_salary_usd - total_deductions)

    return {
        "gross_salary": float(gross_salary_usd),
        "tax_amount": float(tax),
        "social_security_employee": float(nssf_ee),
        "social_security_employer": float(nssf_er),
        "total_deductions": float(total_deductions),
        "net_after_tax": float(net_after_tax),
    }
