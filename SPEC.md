1. Purpose and limits
The tool takes messy road-traffic claim notifications and turns them into approved plain-English updates to claimants. A person decides at two points (Check 1 and Check 2).

The tool must never:
- Use real personal data (the input is synthetic) 
- Value a claim or state an amount of money give legal advice or promise an outcome
- Finalise or allow the final download of an update that a person hasn't approved

2. Input
claim_notifications.csv, 150 rows, produced by generate_claims.py (seed 20261009). 

Columns:
reference, received_date, claimant_name, date_of_birth, postcode, phone, email, accident_date, accident_location, road_user_type, vehicle_registrations, other_driver_insurer, accident_description, injuries_described, time_off_work

vehicle_registrations looks like Claimant vehicle: AB15 CDE; Other vehicle: XY21 ZZZ. Either part may be missing.
road_user_type is one of driver, passenger, cyclist, pedestrian, motorcyclist, or blank.
date_of_birth, road_user_type, vehicle_registrations and other_driver_insurer may be blank.

Required fields: reference, received_date, claimant_name, accident_date, accident_description.

3. Cleaning (SQL, with Python only where SQL can't do it)
Field	Rule
Dates	Accept 2025-04-03, 03/04/25 (day/month/year) and 3rd April. Store as ISO YYYY-MM-DD.
Two-digit years	Received and accident dates become 20YY. A date of birth becomes 19YY if that gives an age of 100 or less, else 20YY.
Dates with no year	Take the year of the received date. If that puts the date after the received date, use the year before.
Postcodes	Uppercase, single space before the last three characters (ch14bq → CH1 4BQ).
Number plates	Uppercase. UK plates become AB15 CDE. Plates in the format AB-123-CD are kept as they are and treated as foreign.
Text fields	Trim leading and trailing spaces.

Rows set aside (status rejected, with a reason): any required field missing or unreadable.

Impossible dates (route Missing information, with a reason): accident date after received date; date of birth after accident date.

4. Duplicates

Two claims are duplicates when all of these hold:

same date of birth and same accident date
same first name, and surnames that are identical or differ by one typo (one letter missing, or two neighbouring letters swapped), or the same email address

Keep the claim with the earliest received date (then the lowest reference). Mark the other duplicate, link it to the one kept, and leave it out of all further steps.

5. LLM extraction

One call per claim, using accident_description and injuries_described. The output must validate against this schema:

Field	Type / allowed values
road_user_type	driver, passenger, cyclist, pedestrian, motorcyclist, pillion, horse_rider, mobility_scooter, unknown
child_involved	true, false, unknown (true if the text says the injured person is under 18)
child_age	integer or null
foreign_vehicle	true, false, unknown (true if the text says the other vehicle is registered abroad)
injuries	list of short strings
contradictions	list of short strings (anything in the text that conflicts with the form fields given)
confidence	high, medium, low
If the output fails validation, retry once. If it fails again, set extraction_failed and send the claim to Check 1.
Timeout: 20 seconds per call.
The prompt is stored as a versioned file (prompts/extract_v1.txt).
The LLM never sees pilot_labels.csv.
6. Triage (Python rules, no LLM)

Work out the facts first, combining the form with the extraction:

Road user: use the form value; if it's blank, use the extraction. If both are filled in and disagree, it's a contradiction, and the more vulnerable of the two is used for routing.
Child: under 18 on the accident date (from date of birth), or child_involved is true.
Foreign vehicle: the other vehicle's plate is in a non-UK format, the insurer name says it's foreign, or foreign_vehicle is true.

Then apply the rules in this order. The first one that matches decides the route:

#	Condition	Route	Reason shown
1	Impossible date, or road user unknown from both sources	Missing information	e.g. "Accident date is after the date received"
2	Accident before 31 May 2021	Solicitor queue	"Accident before the OIC start date"
3	Child or protected party	Solicitor queue	"Claimant is under 18"
4	Vulnerable road user (pedestrian, cyclist, motorcyclist, pillion, horse rider, mobility scooter)	Solicitor queue	"Claimant was a [type]"
5	Foreign-registered defendant vehicle	Solicitor queue	"Other vehicle registered outside the UK"
6	None of the above	OIC-eligible	"Meets the OIC eligibility rules checked by the tool"

Flags (shown at Check 1; they don't change the route):

near limitation: received within 3 months of the accident date plus 3 years
contradiction
low confidence or extraction failed
missing date of birth, insurer or registration
a duplicate was merged into this claim

The value limits (injury up to £5,000, whole claim up to £10,000) are never decided by the tool. Check 1 always asks the person to confirm them.

Each rule is a separate function with its own unit test.

7. Check 1 (route)
Shows: the original notification beside the cleaned fields and the extracted facts; the route, its reason and any flags.
Actions: Confirm route · Change route · Request information.
Changing the route needs a one-line reason. Every action records who acted and when.
8. Claimant update

Drafted by the LLM for every claim that passes Check 1, from the confirmed facts and route only. The prompt is versioned (prompts/draft_v1.txt).

Fixed structure, in this order: what we've received · what happens next · when you'll hear from us next · who to contact.

Automated checks before Check 2 (results shown to the reviewer; a failed check blocks approval until the draft is edited):

every name, date and reference in the draft appears in the claim record
no money amounts (£, "pounds", or any figure next to "compensation")
no outcome promises or legal advice (e.g. "guarantee", "you will win", "you will receive", "we advise you to")
all four sections are present
9. Check 2 (approve)
Shows: the draft beside the claim and the check results.
Actions: Approve · Edit, then approve · Reject (a reason is required; the claim goes back to be redrafted).
Each edit increases the claim's edit_count. The original draft and the final text are both kept.
10. Output

An approved update downloads as <reference>_update.docx (python-docx) containing the reference, the date, the update text, and the footer "Synthetic demonstration data". An update that hasn't been approved can only be downloaded marked "DRAFT – not approved".

11. Claim states

loaded → cleaned → extracted → awaiting_check1 → drafted → awaiting_check2 → approved

Side states: rejected (set aside in cleaning), duplicate, on_hold (more information requested at Check 1).

12. Audit log

One row for every pipeline step and every human action: timestamp, reference, step, prompt_version, output (short summary or JSON), actor (system or user), duration_ms. Rows are only ever added, never changed or deleted.

13. Pages
Page	Contents
Run	Unprocessed claims with checkboxes; Run selected, Run all; a progress indicator
Review	Claims at awaiting_check1 or awaiting_check2, oldest first, opening the check screen
Updates	All updates, newest first, with route and status; view the original claim, edit (reopens Check 2), download
Results	Metrics on the 12 pilot claims: minutes and touches per claim before vs after, route accuracy, edits to drafts, tool time and API cost per claim

Access is by one shared demo password. Every page shows "Synthetic data only".

14. Acceptance tests

The tool is finished when all of these pass:

All 150 rows load; dates, postcodes and plates are in the cleaned formats in section 3.
All 6 duplicate pairs are merged into one claim each, and no non-duplicates are merged.
A claim whose accident date is after its received date gets the route Missing information.
A cyclist, a pedestrian and a child claimant never get the route OIC-eligible.
A claim whose form says "driver" while the text says the claimant was crossing the road is flagged as a contradiction and routed to Solicitor queue.
A claim with French plates mentioned only in the text is routed to Solicitor queue.
Invalid LLM output is retried once and then flagged extraction_failed.
A draft containing a date or name that isn't in the record fails the checks and can't be approved unedited.
A draft containing "£" or "guarantee" fails the checks.
An update can't be downloaded as final before Check 2 approval.
Every step and human action for a claim appears in the audit log.