# DueClaim — Project Context

## What this is
A web app for Indian micro & small enterprises (MSEs) that converts unpaid invoices into a legally quantified recovery claim under the MSMED Act 2006.

## The core value
Given an unpaid invoice, compute the EXACT statutory interest owed under Section 16 of the MSMED Act (compound interest, monthly rests, at 3x the RBI Bank Rate), flag the buyer's exposure under Section 43B(h) of the Income-tax Act, and generate a ready-to-send legal demand notice PDF.

## Non-negotiable engineering rules
1. The interest calculation is DETERMINISTIC PURE PYTHON. An LLM must never compute, adjust, or round any number. LLMs draft human-readable prose only.
2. The interest engine is pure functions with no I/O, fully unit tested, returning a month-by-month breakdown the UI renders for auditability.
3. Manual invoice entry must ALWAYS work. OCR and AI are enhancement paths that may fail without breaking the product.
4. Every user-facing money figure must be traceable to a line in the breakdown.
5. All money is decimal.Decimal. Never float. Anywhere.
6. Scope discipline: this is a 2-day hackathon build. Do not add features not explicitly requested. If you think something is missing, say so and wait — do not build it.

## Stack (fixed — do not substitute)
- Backend: Python 3.12, FastAPI + Mangum, single AWS Lambda, deployed via AWS SAM
- API: API Gateway HTTP API with a Cognito JWT authorizer
- DB: Amazon DynamoDB, single table, PAY_PER_REQUEST
- Frontend: React + Vite + TypeScript + Tailwind CSS
- Hosting: AWS Amplify Hosting
- Auth: Amazon Cognito via @aws-amplify/ui-react <Authenticator>
- OCR: Amazon Textract AnalyzeExpense (not AnalyzeDocument)
- LLM: Amazon Bedrock, Amazon Nova Lite, prose only
- PDF: reportlab
- Region: ap-south-1

## Explicitly OUT OF SCOPE — do not build
Real MSME ODR portal integration or auto-filing; payment gateways; Tally/Zoho/GSTN/bank integrations; agents, vector DBs, RAG, chatbots; billing or subscriptions; mobile apps; any AI that touches arithmetic.

## Repo layout
/backend  — FastAPI app, SAM template, interest engine, tests
/frontend — Vite React app
/docs     — architecture notes, deploy guide, demo script

## Disclaimer requirement
Every generated document and the dashboard must carry: "Estimate only. Not legal advice. Verify Udyam registration status and the date of acceptance of goods/services before relying on these figures."

## Working agreement
After each task, run the tests and show me the real output. Never claim something works without running it. If a command fails, show the full error rather than summarizing it.
