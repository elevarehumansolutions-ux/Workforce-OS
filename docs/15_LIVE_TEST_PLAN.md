# Live test plan (staging), start to end

Purpose: walk the whole product on the live site the way a real company would, in order, and
write down what works and what does not. Work through ONE stage at a time. After each stage,
send the notes (what you did, what you saw, a screenshot if it looks wrong) before moving on.

The live API reports `"environment": "staging"`, so this is a safe place to test. Use a test
company, never a real customer's.

## Before you start

- Use a private/incognito window, so no old login interferes. For two people at once (an HR
  administrator and an employee) use two different browser profiles.
- Test company name: **Zenith Test Ltd**. Make every test email unique and real enough to
  receive mail, for example `yourname+hr1@gmail.com`, `yourname+chidi@gmail.com` (everything
  after the `+` still arrives in your own inbox).
- Keep a simple note per stage: **did / expected / saw**. A screenshot for anything odd.
- Time is UTC on the server and Lagos (UTC+1) on screen.

## Stage 1: Registration, email and login (M2)

1. Open the site, choose sign up, create the first account (this person becomes the owner).
   Expect: a message that a verification email was sent.
2. Open the email, click the link. Expect: the account is verified and you can log in.
3. Log in with the right password. Expect: you land in onboarding (Business DNA), not an error.
4. Log out, log in with a WRONG password. Expect: a clear "invalid email or password" message, no crash.
5. Refresh the page while logged in, then leave it 20 minutes and click around.
   Expect: still logged in (the session renews itself) or a clean return to login, never a blank error.
6. "Forgot password": request a reset, use the email link, set a new password, log in with it.
7. Try signing up again with the same email. Expect: a clear "already registered" message.

## Stage 2: Business DNA and the business plan (M5 + blueprint)

1. Fill Business DNA: company name, industry, what you sell, mission, capital investment (for
   example 25000000), timezone. Save. Expect: you move to **Your business plan**.
2. Wait up to about two minutes. Expect: a "preparing" message, then the plan appears.
3. Check the plan: objectives with key results; departments with a share of the capital that
   adds up to 100%; the by-department chart showing revenue target and estimated profit; clicking a
   department opens its roles and numbers; critical roles marked; KPIs with weight, target and
   plain-words direction; the word "AI" appears nowhere.
4. Skip one department. Expect: its share passes to the others and the total stays 100%.
5. Edit a name, then Add it. Add one position and check its department and boss come with it.
6. Press Accept all. Expect: everything is created, nothing is lost, errors (if any) are listed.
7. Continue to Invite Team. Expect: no old Organization / OKR / KPI steps in the way.

## Stage 3: People, roles and the org-chart picker (M4)

1. Add an employee with "Choose on chart" for position and manager. Expect: the chart opens, the
   new person shows as a dashed box, clicking sets the field.
2. Add three more people across two departments, each with a different manager.
3. Invite one of them to log in (role employee). Open the invite email in the second profile,
   accept, log in as that person. Expect: an employee sees only employee screens (no HR settings).
4. Try to delete a position that has a person in it. Expect: a clear reason, not a crash.

## Stage 4: Strategy and KPIs screens (M6, M8)

1. Open Strategy. Expect: the plan's objectives grouped by department; under each key result the
   KPIs that measure it.
2. Open KPIs for a department. Expect: weight, target, what is good, expected contribution; the
   department's revenue target and profit at the top. Weights add up to 100.
3. Try to make weights add up to more than 100. Expect: refused with a clear message.

## Stage 5: Attendance (M9)

1. As the employee: clock in, then clock out. Expect: times recorded, shown in Lagos time.
2. Clock in and leave it past midnight (or ask me for the helper): expect an automatic close.

## Stage 6: Tasks (M10)

1. As HR/manager: assign a task with a deadline, linked to a KPI, to the employee.
2. As the employee WITHOUT clocking in: open the task. Expect: told to clock in first.
3. Clock in, open it, complete it. Expect: status and time recorded.
4. Create a task with a deadline a few minutes away and let it pass. Expect: it shows overdue and
   the assignee and head get a notification (the scan runs about every 10 minutes).
5. Mark a task blocked with a reason. Expect: the reviewer is notified; approve it; the task is no
   longer overdue.
6. Reassign a task. Expect: the new person is told.

## Stage 7: Workflow and the money figure (M11 + task cost)

1. Build a template with three steps in different departments.
2. Start a case with a client figure (for example 2000000) and NO deadline. Expect: the warning
   before saving; save without a deadline.
3. Start a second case with a figure and a deadline.
4. Let step 1's task go overdue. Expect: the case shows the figure **At risk**, the tracker's Value
   column and the dashboard card agree, and the figure is counted once.
5. Complete step 1. Expect: step 2's task appears for the right person.
6. Cancel the second case with a reason. Expect: the figure shows **Lost**, the open task closes.
7. Check the dashboard totals add up (at risk, lost, secured, on track).

## Stage 8: Notifications and the audit log (M3)

1. Open Notifications. Expect: the events from stages 6 and 7, with working links.
2. Open the audit log as HR. Expect: who did what and when, for the actions above.

## Stage 9: Scoring and dashboards (M12): needs the time helper

Scoring works in quarters, so this stage uses a small helper (written when we reach it) that
creates tasks in the last closed quarter and runs the scoring job by hand. Expect afterwards:
a person's performance card, the department summary with its two numbers, the leaderboard (HR,
executives and managers only), and "no data yet" shown where there is no data, never zeros.

## Stage 10: Settings, roles and limits (M2, M13 not built)

1. As each role (HR, manager, employee) open Settings and the menu. Expect: HR-only screens hidden
   or refused for others, never half shown.
2. Billing and usage: HR only; the usage list shows the plan-generation calls.

## What to send me after each stage

- What you did, what you expected, what happened.
- A screenshot of anything wrong, and the approximate time (so I can find it in the server log).
- If a page says "Couldn't reach server", first check `https://api.workforceos.online/health`
  answers `{"status":"ok"...}`, and tell me.
