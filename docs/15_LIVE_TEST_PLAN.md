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

### Stage 2c: Change history, Undo and Redo (onboarding plan review)

Do this on the plan screen (OS Structure), right after Stage 2, before pressing the last Accept all.

1. After your first change a box appears under the "Accept all" bar: "Last change: ..." with **Undo last
   change** and, after an undo, **Redo**. "All changes (N)" opens the list (newest first, 20 at most).
2. Add a department. Expect "Added department "X"". Undo last change: the department is gone from the real
   structure (check Organization Structure in another tab) and waits again on the plan. Redo: it is back.
3. Merge a suggested department or role into another one. Undo last change: both are separate again, with the
   capital shares they had before. Redo: merged again. Do this in the org chart section too.
4. Edit a role's wording and add it. Undo: it waits again with the ORIGINAL wording. Redo: your wording is back.
5. Skip a department that has roles under it. Undo: the department and everything skipped with it wait again.
6. Add a department, then add one of its roles (two changes). In "All changes", try Undo on the older one:
   expect it is not offered and the reason says to undo the role first. Undo the newer, then the older: both work.
7. Undo two changes, then make a new change. Expect the Redo button and the "undone" lines are gone.
8. Use the Undo button on a card (not the Changes box) for something you added. Expect its line in "All
   changes" reads "undone from its card" and has no Undo.
9. Give someone the role in Add Employee (another tab), then try to undo the change that added the role.
   Expect a refusal in words and nothing changed.

### Stage 2b: Invite Team (the last onboarding step)

Invite Team is about LOGINS, not about the positions accepted in the plan. An invite is an email
plus a system role; the person's department, position and manager are set later, when they are
added as an employee (Stage 3). So you do NOT need one person per accepted role.
1. Send four invites, using plus-addresses that all arrive in your own inbox: `+hr2` as HR
   Administrator, `+manager` as Manager, `+chidi` as Employee, `+exec` as Business Executive.
   Expect: "4 invites sent", each marked "Invite Pending".
2. Try an invite with the email or the role left empty. Expect: a clear message, nothing sent.
3. Invite the same email twice, and invite an email that is already registered. Expect: no crash. An email
   that already has an account (changed 2026-11-13) is NOT added at once: it shows "Invite pending: already has
   an account" and they join by accepting (see Stage 11, step 19). Inviting someone who is already a member of
   your company gives a clear "already a member" message.
4. Press Finish. Expect: you land inside the app (dashboard), and onboarding does not come back.
5. In a second browser profile open one invite email, accept, set a password, log in. Expect: that
   person lands in the app and sees only what their role allows (compare HR, manager, employee).

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

Scoring works in quarters, so this stage uses the helper `backend/scripts/admin/stage9_time_helper.py`
(commands, with line-by-line explanations, in `14_PRODUCTION_TROUBLESHOOTING.md` section 12). It runs
the REAL nightly job as if it were another date, on the TEST company only. No fiscal month is changed.
1. Before running it, have real data in the current quarter (Q4 2026, Oct to Dec): tasks done on time,
   late and not done, linked to KPIs; manual KPI results; and one department whose KPI weights add up to
   LESS than 100 (for example one KPI at 70%).
2. Run `show`, then `run --on 2027-01-02`. Expect `closed_previous_period: True`.
3. Open Performance for the quarter 2026-10-01 to 2026-12-31: a person's performance card, the
   department summary with its two numbers (the short department says "Scored on 70% of its KPI
   weights" and its score is not lowered), the leaderboard (HR, executives and managers only), and "no
   data yet" wherever there is no data, never zeros.
4. As an HR administrator open Notifications: ONE "A department's KPI weights are not at 100%" for the
   short department; its link opens the KPIs screen on that department. Run `run --on 2027-01-03` again:
   no second reminder.
5. Two weeks before a quarter the KPIs screen shows an amber note for a short department (the real date
   must be within 14 days of 1 Jan/Apr/Jul/Oct, so this is checked by reading the code and the unit test,
   not live, unless you test in mid-December).
6. `unfreeze --quarter-start 2026-10-01`, add one more task, `run` again: the figures change.

## Stage 10: Settings, roles and limits (M2, M13 not built)

1. As each role (HR, manager, employee) open Settings and the menu. Expect: HR-only screens hidden
   or refused for others, never half shown.
2. Billing and usage: HR only; the usage list shows the plan-generation calls.

## Stage 11: Re-test of the problems found during testing (do this AFTER Stage 10)

Each one is a problem found in a live test and fixed on 2026-11-11 (numbers refer to the to-do in
`09_PROGRESS.md`). Do them last so they do not change the flow of the stages above. Deploy the branch
first (`alembic upgrade head`, restart the API and Celery, hard refresh the browser). For each: do
what is described, and send what you saw.

**A. Messages and labels**
1. (9) Add an employee with the work email left empty or typed without an "@". Expect "Work email: Enter
   a valid email address, for example name@company.com", NOT "Validation failed". Try the same in Invite
   Team with `ssssss`.
2. (4) Add your own objective, then "+ Add a key result". Expect the date field to be labelled "Achieve
   this by (optional)".
3. (11) As a SECOND HR account, and as a business executive, open the dashboard "Recent activity" and
   Settings > Audit Log. Expect sentences with real names ("Ada sent a team invite"), not "Someone
   invite invite".

**B. Adding people**
4. (12, 13) Add an employee. Expect "Save and add another" to stay on the form with a green "Added X" and
   keep the role and start date, and "Save and finish" to go to the directory (not the profile page).
5. (12) In the manager dropdown expect "Name, Position (Department)". With the boss role empty expect a
   note "Nobody holds ... yet", and in "Choose on chart" empty roles marked "Vacant".
6. (12 step 2) Add the boss LAST: add a Sales Rep first, then their Head of Sales. Expect the rep to
   report to the head without you choosing it, and the green notice to say so. Give someone a manager by
   hand, then add their boss: that person must NOT change.
7. (14) Add two people to one role. Expect a warning "the role will then be shared", the chart tag "shared
   by 2", and no automatic manager link through that role.
8. (15) Organization Structure: the roles chart at the bottom lists who holds each role (or "Vacant"); each
   department with no head and one person in its top role shows "Suggested: X ... Make them head"; the Head
   dropdown shows "Name, Position".

**C. The business plan (onboarding wizard, or "Prepare a new set")**
9. (1) Add a department, then press **Undo** beside "Added". Expect a window counting what goes with it;
   after Undo everything is waiting again and can be added a second time.
10. (1) Add a role by hand under an added department, then Undo that department. Expect a refusal naming
    the reason, and nothing changed.
11. (2) Merge one suggested department into another. Expect "You merged X into this. Undo merge" on the
    target. Press it: the plan is exactly as before. Merge again, add the target: Undo merge is refused.
12. (3) Skip a department. Expect its roles, objectives, key results and KPIs to show "Skipped" at once.
13. (5, 6, earlier) KPI step: make the weights of one department add up to less than 100, then delete the
    last KPI. Expect it to be allowed, with "X% unused".

**D. Menu, profile and phone**
14. (10) Click your name at the bottom of the menu. Expect "My profile" and "Sign out". Open My profile:
    your details, change password, sign out.
15. (10) Make the browser window narrow (or use a phone). Expect a top bar with a ☰ button that opens the
    menu. Walk every screen at that width and write down each one that breaks (tables, org chart, wizard,
    KPI forms): each becomes its own to-do. This is the one item that is not finished: it needs your eyes.

**D2. The people flow (added 2026-11-13; use plus-address emails you can read)**
17. (16) Open the dashboard's Recent activity and Settings > Audit Log after adding an employee and sending an
    invite. Expect "added employee Chidi Okafor (chidi@x.com)" and "invited chidi@x.com", never just "added an
    employee".
18. (17) Invite a teammate WITH a name ("Ngozi Eze"). Open the invite email: the page says "Join <company>" and
    shows the name already filled in; you only choose a password. Invite another WITHOUT a name: the page asks for it.
    From Add Employee, tick "give login access": the accept page shows the employee's name too.
19. (21) Make a mistaken account: sign up a plus-address as a new company, verify it. As HR of your test
    company, invite THAT email. Expect: "Invite pending: already has an account, they confirm with their
    password"; the person is NOT in Team Management yet. Open the invite email: the page asks only for the
    existing password. After joining, their name menu shows "Switch company (2)" and the company name; the
    switch screen opens either company. In the new company they have the role you gave, in their own one they
    are still HR.
20. (21) Invite the same email again: "already a member". Deactivate them in Team Management: their switch into
    that company is refused.
21. (19) Invite a teammate from Invite Team (no employee record). Open Employees: the amber box says "1 person has a
    login but no employee record" with "Create employee record"; the button opens Add Employee with the name and
    email filled in and the login already linked. Team Management shows "No, create one" before and "Yes" after.
22. (18) On Add Employee choose a department's top role, tick "Make this person head of <department>". Expect, if
    the department already has a head, "currently headed by X. Ticking this replaces them", and the login role
    set to Manager. Save, open Organization Structure: the head is shown.
23. (5, 18) Open Employees > Org chart. Expect every role with its people, "Vacant", "shared by 2", a star on
    each head. Click a person: open profile, make head of their department, change their access level; the
    chart updates.
24. (24) With a second browser profile, sign up as a founder and stay on the Business DNA step. From another
    company, invite that email. Open the invite link in the founder's browser and enter the password. Expect
    "You've joined X. Nothing changed in the company you were working in". Go back to the Business DNA page and
    save it: it must save without "insufficient permission". Name menu > Switch company (2) opens the other one,
    and switching back works.
25. (22) Employees page, signed in as the founder who has no employee record: your own row says "This is you" and
    the button reads "Create your employee record"; it opens Add Employee with your details filled in.
26. (23) In the org chart, make someone else head of a department that already has a head who has a login. Expect
    the green message plus "X is no longer head of Sales. Their access level is still Manager. Change it"; the
    button opens X so you can change the level. On Add Employee with "Save and add another" the saved message
    says the same. The same amber note (added later, to-do 29) also appears on Organization Structure when you
    change a department's head in the Head dropdown; its "Change it" opens Team Management.
27. (25) Onboarding, first page: the Business DNA box lists vision, mission, core values, business model, revenue
    drivers, operational drivers, customer value drivers and performance philosophy, in the label and in the
    placeholder.

28. (28) With ONE company, open the name menu: "Companies" is there. Open it: "Start another company", "You own 1
    of 3". Type a name and "Create and open it": you land on that company's Business DNA, empty. Open the menu
    again: "Switch company (2)"; switching back shows the first company with its own people. Create the same
    name again (any capitals): refused in words. Create a third company, then try a fourth: the button is
    disabled at 3 and says why. Double click "Create and open it" once on a fresh name: only one company appears.

**E. Scoring (needs the helper in Stage 9)**
16. (7, 8) Done inside Stage 9: the reminder for a department below 100% and "Scored on X% of its KPI
    weights".

## What to send me after each stage

- What you did, what you expected, what happened.
- A screenshot of anything wrong, and the approximate time (so I can find it in the server log).
- If a page says "Couldn't reach server", first check `https://api.workforceos.online/health`
  answers `{"status":"ok"...}`, and tell me.
