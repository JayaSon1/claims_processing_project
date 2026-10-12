GOAL
To build a deployed tool that automates the first stage of a tariff-claim engine: messy claim notifications go in, approved plain-English claimant updates come out. A person decides at two points, and there's a before-and-after number

INPUT: 150 synthetic road-traffic claim notifications in 'claim_notifications.csv'. Generated from 'generate_claims.py'. No real data.

PROCESS:
1. Import the csv into SQLite 
2. Clean the SQL database:
    - Fix the date formats, postcodes and number plates
    - Flag impossible dates
    - Flag rows missing required fields with a reason
3. In SQL remove duplicates, matching on name, date of birth and accident date, keep the first but flag the duplicates
4. Use an LLM to read the free-text description and returns information for fixed fields and validates output. One retry of the process is allowed if the first output was incorrect, if still incorrect then it is flagged for human review
5. Applies OIC portal eligibility rules to the claims using rules coded in python (See OIC Triage rules). The output is the one of the following routes and a reason (Routes: OIC-eligible, Solicitor queue, Missing information)
6. Includes human invervention after a route is selected. A reason is needed to change the route
7. The LLM creates a plain-English update to the claimant which automated checks are run on:
    - Every name, date and reference in the draft exists in the claim record
    -  No outcome promises, money amounts or legal advice
    - Fixed structure: what we've received, what happens next, when you'll hear from us, who to contact
8. A human must approve the claimant update before it is finalised. The human can edit then approve, approve or reject at this stage
9. The claimat update document can then be downloaded as a word doc

TOOL OUTPUT: A plain-English update to thelaimant that can be downloaded as a word doc

OIC Triage rules:
A claim is OIC-eligible only if:
1. The accident happened on or after 31 May 2021
2. The claimant is not a child or a protected party
3. The claimant is not a vulnerable road user (pedestrian, cyclist, motorcyclist, pillion passenger, horse rider, mobility-scooter user)
4. The defendant's vehicle is registered in the UK

The value limits (injury up to £5,000, whole claim up to £10,000) are confirmed by the person at Check 1, not by the tool. Claims close to the 3-year limitation date, contradictions and low-confidence extractions are flagged for the person.

Logging
Every step and every human decision writes one row to an audit log: claim reference, step, prompt version, output, who acted, time taken

The web pages
Kept minimal. The pages exist to show the tool working.

Run: list of unprocessed claims; Run selected or Run all
Review: claims waiting for Check 1 or Check 2
Updates: all claimant updates, newest first, with the route and status; view the original claim, edit, or download as Word
Results: the numbers below

No accounts. One shared demo login and password 

Measuring it (Results)
On the 12 hand-labelled pilot claims:

Metrics to record
- Minutes per claim: before vs after	        Before: time yourself doing them by hand. 
        After: time the two checks
- Touches per claim: before vs after	Count of human actions
- Route accuracy: Tool's route vs your labels
- Edits to drafts: Number of times a draft was changed before approval
- Tool time and API cost per claim: From the audit log


Stack
Python 3.11, Flask, SQLite, Pydantic, one LLM API, python-docx, Render

API key in environment variables only; spend limit set on the API account

Build order
1. Load, clean, de-duplicate
2. Extract facts and triage, with a test for each rule
3. Check 1 and the Review page
4. Draft, checks, Check 2
5. Updates page and Word download
6. Audit log and Results page
7. Deploy
8. Run the 12-claim pilot and record the numbers
