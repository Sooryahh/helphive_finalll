# HelpHive — Genesis 2.0 Duplicate Warning Update

This package is prepared from the current `Sooryahh/genesis_helphive` main-branch files.

## What it adds

1. White + orange interactive UI.
2. Responsive mobile navigation.
3. Animated opportunity cards and reveal effects.
4. Password show/hide.
5. Auto-dismissable flash messages.
6. Double-submit protection.
7. Organizer duplicate detection before creating an opportunity.
8. Duplicate detection when editing an opportunity.
9. Existing opportunity preview with similarity percentage.
10. "Create anyway" confirmation flow.
11. Explicit duplicate-registration protection for students.
12. Existing SQLite UNIQUE(user_id, opportunity_id) protection remains in place.

## Duplicate algorithm

The duplicate warning combines:
- title similarity: 55%
- location similarity: 20%
- same event date: 15%
- same category: 10%

A likely duplicate is shown when the weighted score is high enough or when date/location match strongly with a reasonably similar title.

## Important

No GitHub commit or push was made by this package.

Recommended workflow:
1. Back up your current folder.
2. Copy these files into the matching paths in your local repository.
3. Run `python app.py`.
4. Test the complete flow.
5. Run `git diff`.
6. Only after you approve the changes, commit and push to `main`.

## Demo for the challenge

Create:
Campus Clean-Up Drive
25 September
FISAT Campus
Environment

Then try:
Campus Cleanup Drive
25 September
FISAT Campus
Environment

The system should show "Possible duplicate detected" and allow:
- View existing
- Review details
- Create anyway

Then register as a student and attempt to register a second time. The system should block the duplicate application.


## Volunteer experience + feedback update

13. Student volunteer experience dashboard based on verified attendance.
14. Experience metrics: attended events, causes/categories explored, and an experience level.
15. Volunteer feedback form available after an organizer marks the student as present.
16. 1–5 rating plus written experience comment.
17. One feedback record per volunteer per event, with the ability to update feedback.
18. Organizer feedback view with average rating, response count, and volunteer comments.

### How experience is calculated
Experience is derived from participation records rather than self-entered claims. Each event where `attendance=1` counts as an attended event. The dashboard also counts distinct opportunity categories.

### Feedback flow
1. Student registers for an opportunity.
2. Organizer approves the registration.
3. Organizer marks the student as Present.
4. The student's dashboard unlocks **Give feedback**.
5. Student submits a 1–5 rating and comment.
6. The organizer can view aggregate ratings and individual feedback from the opportunity dashboard.
