# DueClaim — submission writeup

Live: https://main.d3aaarf67tciji.amplifyapp.com · Source: https://github.com/vikky781/DueClaim

## The problem

India's micro and small enterprises are, in effect, involuntary lenders to their customers. The Economic Survey 2025-26 estimates **₹8.1 lakh crore** stuck in delayed MSME payments. Parliament dealt with this in 2006: the MSMED Act fixes a hard 45-day payment window (s.15), imposes compound interest at three times the RBI Bank Rate with monthly rests for every day beyond it (s.16), and makes those terms override any contract (s.24). Since 2023, s.43B(h) of the Income-tax Act adds a second lever — a buyer cannot deduct an MSE payable until it is actually paid.

The remedy exists. It is barely used, for two mundane reasons: the number is hard to compute correctly (monthly rests, rate changes, partial months, part-payments), and a phone call saying "you owe us interest" carries no weight. A demand letter with a line-by-line statement of interest under the Act does.

## What DueClaim does

1. **Enter an unpaid invoice** — by hand (always works), or by dropping a photo/PDF of it; Textract proposes the invoice number, date, buyer and total, each with a confidence score, for the user to check. The *date of acceptance* is never auto-filled: it starts the statutory clock and is a determination the supplier must make.
2. **See the claim** — the dashboard's single dominant figure is the total recoverable today: principal plus statutory interest, with "accruing ₹X per day". Per-buyer rollups carry a **43B(h) exposed** badge when the buyer is a company and payment is overdue.
3. **Audit it** — every invoice shows the month-by-month statement: rest period, days, rate applied, accrual basis, interest, closing balance, and whether that month capitalised. Every number on screen is on that table.
4. **Send it** — one click produces a formal demand notice PDF: sender and Udyam number, addressee and GSTIN, the facts, the demand, the statutory basis, a figures block, the full statement as a bordered table, the Facilitation Council / MSME ODR closing, signature block, and the disclaimer on every page. The PDF is stored and a one-hour link opened.

## AWS services and what depends on each

| Service | Exactly what breaks without it |
|---|---|
| **Lambda** (Python 3.12, one function, FastAPI via Mangum) | Everything behind `/api/v1`: invoice CRUD, the portfolio summary, OCR extraction, notice generation. The interest engine runs here on every read. |
| **API Gateway HTTP API** | The public edge. Its **Cognito JWT authorizer** rejects unauthenticated calls before Lambda runs, and its CORS configuration answers browser preflights (explicit GET/POST/PATCH/DELETE routes — an `ANY` route would have sent `OPTIONS` to the authorizer and broken every browser call). |
| **Cognito User Pool** | Sign-up / sign-in with email. The `sub` claim from the ID token is the tenant key for every DynamoDB item, so users can only ever read their own invoices. |
| **DynamoDB** (single table, on-demand) | Persistence of the business profile, invoices and the log of generated notices. Money round-trips as `Decimal` with no precision loss; interest is deliberately never stored. GSI1 keys invoices by normalised buyer name for the per-buyer rollup. |
| **S3** (one bucket, public access blocked, 7-day lifecycle) | Two things: the browser's direct presigned `PUT` of an invoice scan for OCR (`uploads/{sub}/…`), and the generated demand-notice PDFs served via presigned `GET` (`notices/{sub}/…`). |
| **Textract `AnalyzeExpense`** | The OCR accelerator on the invoice form. Its `INVOICE_RECEIPT_ID`, `INVOICE_RECEIPT_DATE`, `RECEIVER_NAME`/`VENDOR_NAME` and `TOTAL` summary fields become proposals with confidence; defensive parsers handle `DD/MM/YYYY`, lakh-grouped amounts and `Rs.`/`INR`/`₹` prefixes, and return `null` rather than guess. |
| **Amplify Hosting** | Builds and serves the React frontend from `main`; the three `VITE_*` variables and the SPA rewrite live there. |
| **AWS SAM / CloudFormation** | The whole backend is one template: pool, client, table, bucket, API, function, IAM. `sam build && sam deploy` is the entire release process. |

## Engineering choices worth defending

**The arithmetic is pure, tested Python.** `dueclaim/engine.py` has no I/O and no dependencies beyond `decimal` and `datetime`. Its convention is written out clause by clause in the module docstring — rest boundaries anchored to the appointed day with end-of-month clamping, `interest = accrual_basis × 3 × bank_rate ÷ 100 × days ÷ 365`, capitalisation only at completed rests, a simple uncapitalised final partial period, mid-period rate changes split by day segment — and 25 tests pin every clause, including leap-year February, rate splits inside the final period, and the reconciliation invariants (every row's closing balance equals its basis plus the period's running interest; the last row closes at the total recoverable; the sum of the interest column *is* the total).

**Decimal everywhere, quantized once.** Along the way the tests caught that Decimal addition is not associative at 28 digits — two summation orders of the same rows differed in the last place. Every aggregate now derives from a single chain, and quantization to paise happens exactly once, at the serialization boundary. The frontend never parses money into a float: it groups the API's 2-dp strings character by character.

**Interest is never stored.** Every read recomputes as of today, or as of `?as_of=` for the demo. The dashboard, the statement and the notice cannot drift apart because there is only one source.

**OCR proposes, never decides.** Textract's output is mapped into typed proposals with confidence; anything under 80% is marked "check this"; unparseable text comes back `null` with the raw reading attached. Testing against a real invoice showed Textract tagging the amount-in-words line as `TOTAL` at higher confidence than the numeric total — the mapper now prefers the highest-confidence reading that actually parses. Nothing from OCR is persisted until the user submits the form.

## What I learned

* **Browsers preflight; curl doesn't.** The API passed every curl test and failed the first real browser call. `ANY /api/{proxy+}` matched `OPTIONS`, which the JWT authorizer rejected. Explicit method routes let the gateway answer preflight itself.
* **Presigned URLs need the regional endpoint.** botocore's default emitted `bucket.s3.amazonaws.com`; S3 answered the browser's `PUT` with a 307 it could not follow. `s3v4` + virtual-hosted addressing fixed it, and a test now pins the host.
* **Fixed-precision arithmetic has a summation order.** "Sum of the rows equals the total" is only exact if the total *is* that sum.
* **A legal document's credibility is its table.** The demand notice without the statement is a letter; with it, it is a claim.

## Scope decisions

**Bedrock was scoped out.** Model access in the account was not granted in time, so the LLM prose path was never built. Having built the deterministic version, I would make the same call with access: a demand notice is a legal instrument whose every sentence may be read out in a Facilitation Council hearing. A template whose text is fixed, whose figures come from a tested engine, and whose output is byte-for-byte reproducible is *better* for that job than generated prose — there is nothing in it that could be hallucinated, softened or embellished. The `prose` parameter on the renderer exists as the slot for optional human-written context; it is not wired to a model.

Also deliberately out: real ODR portal filing, payment collection, Tally/GSTN integrations, multi-page Textract, and any AI that touches arithmetic.

**Known limits.** The RBI Bank Rate table is seeded with the current rate only; invoices that would accrue before 6 Dec 2025 are refused with a clear error rather than priced with a rate we don't have. Historical entries go in one list in `dueclaim/rates.py`.

## Verification

Backend: 194 tests (engine, money, models, store via moto, auth, routes, OCR parsers and mapping, uploads, notice PDF via text extraction, notice route). Frontend: 10 (money formatter incl. 16-digit exactness, validation mirroring the backend). Every feature was exercised in a real browser against the deployed stack before commit: sign-in, business gate, manual entry, OCR on a rendered GST invoice, dashboard figures cross-checked against the engine, and the generated PDF downloaded from S3 and rendered.
