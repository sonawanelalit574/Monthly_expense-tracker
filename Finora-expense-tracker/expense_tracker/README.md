# Finora

Flask workspace for **personal**, **business**, and **student** money: salary, phone/cash spend, then SIP, financial saving, and EMI from what is left. Includes a country-wise currency converter and a PIN-locked password vault.

Start empty. Register with email, or use **Continue with Google** after setting `GOOGLE_CLIENT_ID` (and secret for the redirect flow) in the environment.

Salary entries generate a bank credit code such as `FN-SAL-20260901-148000-A1B2C3` from the credit date.

CSV import accepts bank-style files (`date`, `description`, `debit`/`credit` or `amount`) and converts them into phone/cash/bank transactions.

## What is inside

## Run

```bash
cd expense_tracker
pip install -r requirements.txt
python run.py
```

Open [http://127.0.0.1:5010](http://127.0.0.1:5010), create a workspace, and sign in with the email you registered.

## What is inside

- Salary / revenue / stipend ledgers
- Monthly expenditures with UPI, cash, card, and bank channels
- Donut of spend vs SIP vs saving plans vs EMI vs leftover
- After-savings: SIP projector, goals/emergency funds, EMI calculator
- Budgets, recurring bills, memos, CSV export
- Live FX by country (with offline fallback)
- Encrypted password vault
