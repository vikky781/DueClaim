# DueClaim

**Turn an unpaid invoice into a legally quantified recovery claim under the MSMED Act, 2006.**

Live app: **https://main.d3aaarf67tciji.amplifyapp.com**
API: `https://enbgog7uh4.execute-api.ap-south-1.amazonaws.com` (`/health` is public; everything else needs a Cognito token)

DueClaim is for Indian micro and small enterprises (MSEs). Give it an unpaid invoice and it computes the **exact statutory interest** the buyer owes — compound, monthly rests, three times the RBI Bank Rate — shows the month-by-month statement that produced the figure, flags the buyer's income-tax exposure, and generates a formal demand notice PDF ready to send.

---

## The problem

Delayed payments are the single largest working-capital drain on small Indian manufacturers and service providers. The Economic Survey 2025-26 puts the sum locked up in delayed MSME payments at **₹8.1 lakh crore**. The law already compensates suppliers for this — generously — but almost nobody claims it, because computing the figure correctly is fiddly, and putting it in a form a buyer's finance team will take seriously is harder still.

## The statutory basis

| Provision | What it says | What DueClaim does with it |
|---|---|---|
| **MSMED Act s.15** | The buyer must pay on the agreed date, and in no case later than **45 days** from the day of acceptance (or deemed acceptance). That date is the *appointed day*. | `appointed_day = acceptance + min(agreed_credit_days or 45, 45)` |
| **MSMED Act s.16** | Failing that, the buyer owes **compound interest with monthly rests** from the appointed day at **three times the Bank Rate** notified by the RBI, regardless of anything agreed between the parties. | The interest engine: pure Python, `Decimal` throughout, monthly rests anchored to the appointed day, every rest period returned as an auditable row. |
| **MSMED Act s.24** | Sections 15–23 override anything inconsistent in any other law. | Quoted in the demand notice; the reason "but our contract says 90 days" doesn't help the buyer. |
| **Income-tax Act s.43B(h)** | A buyer cannot deduct an MSE payable as an expense until it is actually paid, if paid outside the s.15 window. | Corporate buyers with overdue invoices are badged **43B(h) exposed** on the dashboard and reminded of it in the notice. |

The engine's exact convention (rest boundaries, clamping, rate changes, the final partial period, what "closing balance" means) is documented in full in `backend/dueclaim/engine.py`'s module docstring and pinned by 25 tests.

Everything in the product carries the same disclaimer: *Estimate only. Not legal advice. Verify Udyam registration status and the date of acceptance of goods/services before relying on these figures.*

---

## Architecture

```
                         ┌──────────────────────────────────────────────────┐
                         │  Browser  ·  React + Vite + TypeScript + Tailwind │
                         │  <Authenticator> (Amplify UI, themed)            │
                         └───────┬──────────────────────────┬───────────────┘
                                 │ id token (JWT)           │ presigned PUT (invoice scan)
                                 ▼                          ▼
   ┌──────────────────────────────────────────┐   ┌──────────────────────────────┐
   │  API Gateway HTTP API   ap-south-1       │   │  S3  dueclaim-uploads-…      │
   │  · Cognito JWT authorizer (all /api/*)   │   │  · uploads/{sub}/…  (OCR in) │
   │  · CORS preflight answered by the gateway│   │  · notices/{sub}/…  (PDF out)│
   └──────────────────┬───────────────────────┘   │  · public access blocked     │
                      │                           │  · 7-day lifecycle           │
                      ▼                           └──────────────┬───────────────┘
   ┌──────────────────────────────────────────┐                  │
   │  Lambda (Python 3.12)  FastAPI + Mangum  │◄─────────────────┘
   │                                          │
   │   app/routes/invoices.py  CRUD, summary  │      ┌───────────────────────┐
   │   app/routes/uploads.py   presign,extract│─────►│  Textract             │
   │   app/routes/notices.py   PDF generation │      │  AnalyzeExpense       │
   │   app/notice.py           reportlab      │      └───────────────────────┘
   │                                          │
   │   dueclaim/engine.py  ◄── pure, no I/O   │      ┌───────────────────────┐
   │   dueclaim/rates.py       RBI Bank Rate  │─────►│  DynamoDB  single table│
   │   dueclaim/money.py       quantize once  │      │  PK USER#sub · SK INV#│
   └──────────────────────────────────────────┘      │  GSI1 by buyer        │
                                                     └───────────────────────┘
   ┌──────────────────────────────────────────┐
   │  Cognito User Pool  (email sign-in)      │   Hosting: AWS Amplify (main branch)
   └──────────────────────────────────────────┘   Infra:   AWS SAM (backend/template.yaml)
```

Design rules that shaped it (see `CLAUDE.md`):

* **The arithmetic is deterministic pure Python.** No model computes, adjusts or rounds a number. There is no LLM in the product.
* **Interest is never stored.** Every read recomputes as of today (or `?as_of=`), so the dashboard and the notice can never disagree.
* **All money is `Decimal`**; quantization to paise happens once, at the serialization boundary. Every figure a user sees is traceable to a row in the statement.
* **Manual entry always works.** OCR is an accelerator that proposes values with confidence scores; it never writes anything.

---

## Repository

```
backend/    FastAPI app, SAM template, interest engine, tests (194)
  dueclaim/   engine.py · rates.py · money.py       ← the pure core
  app/        models · store · auth · ocr · notice · routes/
  scripts/    seed_demo.py
frontend/   Vite React app (dashboard, invoice entry with OCR, statement, notice)
docs/       WRITEUP.md
```

## Local setup

Backend (Python 3.12):

```sh
cd backend
python -m venv venv && venv/Scripts/activate      # or source venv/bin/activate
pip install -r requirements-dev.txt
pytest                                            # 194 tests, no AWS needed (moto + fakes)
```

Frontend (Node 20+):

```sh
cd frontend
cp .env.example .env     # VITE_API_URL, VITE_USER_POOL_ID, VITE_USER_POOL_CLIENT_ID from the stack outputs
npm install
npm test                 # money formatter + validation
npm run dev              # http://localhost:5173
```

## Deploy

Backend — one stack, `dueclaim-dev`, region `ap-south-1` (parameters baked into `backend/samconfig.toml`):

```sh
cd backend
sam build && sam deploy
```

Outputs: `ApiUrl`, `UserPoolId`, `UserPoolClientId`, `TableName`, `UploadBucketName`.

Frontend — Amplify Hosting builds `frontend/` from `main` on push. It needs the three `VITE_*` variables set under *App settings → Environment variables* and the SPA rewrite `/<*> → /index.html (404-200)`.

Demo data for a signed-up user:

```sh
cd backend
venv/Scripts/python scripts/seed_demo.py --sub <cognito-sub> --replace
```

## Known limits

* `dueclaim/rates.py` is seeded with the current RBI Bank Rate only (5.50% from 6 Dec 2025). Invoices whose interest would begin before that are refused with a clear error rather than priced wrongly; historical entries go in that one table.
* Textract `AnalyzeExpense` is called synchronously: single-page PDFs and images only.
* The demand notice is a deterministic template — deliberately. See `docs/WRITEUP.md`.

## Licence

MIT — see `LICENSE`. Fonts under `backend/app/fonts/` are DejaVu (Bitstream Vera licence, included).
