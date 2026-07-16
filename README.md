# Accountability Bot

<p align="center">
  <img src="assets/telegram-bot-mascot.png" alt="Telegram Accountability Bot mascot" width="320" />
</p>

A friendly Telegram bot that helps a group stay accountable with daily goals, targeted reminders, status updates, and a monthly leaderboard.

Use the bot here: **[@be_accountable_bot](https://t.me/be_accountable_bot)**

## What the bot does

`@be_accountable_bot` runs a simple daily accountability challenge:

1. Participants submit **exactly 3 goals** in the morning.
2. Participants report how many goals they completed at night.
3. The bot tracks who passed or failed each day.
4. `/score` shows the current month leaderboard ranked by fewest failed days.

It is designed for a Telegram group. Any group member who wants to participate can register; people who do not register are not tracked or tagged.

It does **not** run in private messages. If you PM the bot, it will explain that it needs to be added to a group first.

## Quick start

### 1. Add the bot to your Telegram group

Create or choose a Telegram group, then add **[@be_accountable_bot](https://t.me/be_accountable_bot)** to that group.

Once the bot joins, it will introduce itself and explain the basic flow.

### 2. Register yourself

Each participant should send this once in the group:

```text
/register
```

Example response:

```text
✅ Registered Ernest
Participants: 3

Current participants
1. Ernest
2. Cyril
3. Alice
```

### 3. Submit your 3 daily goals

Every morning, submit exactly 3 goals using `/goals`.

```text
/goals
- 3x leetcode
- gym
- read
```

You can also write numbered goals:

```text
/goals
1. finish assignment
2. go for a run
3. sleep before midnight
```

The bot will record your goals and show them back to you.

If you report `/done 3`, the bot invites you to plan ahead. A `/goals` submission sent before the next calendar date begins is saved as a draft for the next check-in date. You can overwrite it by sending `/goals` again.

The next morning, either promote that draft:

```text
/confirmgoals
```

or send a fresh `/goals` submission. Fresh goals become today's official goals and replace the draft.

### 4. Report your completion

At night, report how many of your 3 goals you completed:

```text
/done 2
```

Valid options are:

```text
/done 0
/done 1
/done 2
/done 3
```

Completing **2/3 or 3/3** goals is a pass ✅.

Completing **0/3 or 1/3** goals is a fail ❌.

## Daily schedule

All times are in **Singapore time**.

| Time | What happens |
|---|---|
| 8:00 AM | Morning reminder; drafted participants are asked to confirm or replace, while participants with no goals are tagged separately |
| 9:30 AM | Final goal reminder with the same draft/no-goals distinction |
| 10:00 AM | Goal deadline summary posts if anyone is still missing |
| Before 10:00 AM | If all registered participants submit early, the goals summary posts immediately |
| 8:00 PM | Completion reminder tagging only participants who have not reported `/done` |
| 10:00 PM | Final completion reminder tagging only participants who have not reported `/done` |
| 5:00 AM next day | Completion deadline and daily close |

If you do not submit goals by **10:00 AM**, the day counts as failed.

New participants who register after **10:00 AM** start from the next day. They are not tagged as missing or failed for that same date; if they choose to submit same-day goals, those goals are accepted without the late penalty.

If you do not report completion by **5:00 AM the next day**, the day counts as failed.

## Commands

| Command | What it does | Example |
|---|---|---|
| `/register` | Join the accountability challenge | `/register` |
| `/goals` | Submit exactly 3 goals for today | `/goals` followed by 3 lines |
| `/confirmgoals` | Promote a draft for today into official goals | `/confirmgoals` |
| `/done 0` | Report that you completed 0 goals | `/done 0` |
| `/done 1` | Report that you completed 1 goal | `/done 1` |
| `/done 2` | Report that you completed 2 goals | `/done 2` |
| `/done 3` | Report that you completed all 3 goals | `/done 3` |
| `/today` | Show today's goals and status | `/today` |
| `/score` | Show current month leaderboard | `/score` |
| `/summary` | Same as `/score` | `/summary` |
| `/remove` | Remove an inactive participant from this group | `/remove @username` |
| `/rules` | Show the challenge rules | `/rules` |
| `/help` | Show command help and examples | `/help` |

## Goal examples

Good goal submissions have **exactly 3 goals**, one per line.

```text
/goals
- settle course registration
- chest and back workout
- read 20 pages
```

```text
/goals
1) finish work presentation
2) run 5km
3) call parents
```

The bot preserves your goal text. For example, `3x leetcode` stays as `3x leetcode`.

## Checking today's status

Use:

```text
/today
```

Example output:

```text
Daily Status — 09 Jul 2026

cyril
Status: ⏳ Pending
Progress: not reported
Goals
1. settle course registration
2. chest and back
3. read

Ernest
Status: ✅ Pass
Progress: 2/3
Goals
1. 3x leetcode
2. gym
3. read
```

Status meanings:

| Status | Meaning |
|---|---|
| ⏳ Pending | The day is still in progress |
| ✅ Pass | Completed at least 2 out of 3 goals |
| ❌ Fail | Missed goals, missed completion report, or completed fewer than 2 goals |

## Monthly leaderboard

Use:

```text
/score
```

The bot counts failed days for the current month and ranks participants by fewest failed days.

Example:

```text
🏆 Leaderboard — July 2026
━━━━━━━━━━━━
1. Ernest — 0 failed days — $0
2. Friend — 1 failed day — $5
3. Third — 3 failed days — $15

Group total: $20
```

There is no two-person net settlement. The leaderboard simply shows each participant's failed-day count and penalty total using the configured amount, currently `$5` per failed day.

## Removing inactive participants

Use `/remove` to stop tracking an inactive participant in the current group:

```text
/remove @username
```

or:

```text
/remove Display Name
```

Removal is scoped to the current Telegram group. It does not delete that user's membership in other groups.

## Quote of the day

When everyone has submitted their goals before the 10:00 AM deadline, the bot sends a group goals summary with a **Quote of the Day**.

At 10:00 AM, if some participants are still missing, the bot posts the submitted goals so far and tags only the missing participants.

The quote comes from an external quote API. If the quote service is temporarily unavailable, the bot will still send the goals summary.

## Friendly tips

- Submit your goals early so you do not get tagged by reminders.
- Keep goals concrete and easy to judge at night.
- Use `/done 2` or `/done 3` as soon as you know you have passed the day.
- Use `/today` anytime to check what is still pending.
- If Telegram offers the bot command menu, you can tap commands instead of typing them.

## Common mistakes

### Sending fewer or more than 3 goals

The bot expects exactly 3 goals.

Good:

```text
/goals
- study
- workout
- read
```

Not valid:

```text
/goals
- study
- workout
```

### Forgetting `/done`

Submitting goals is only the morning check-in. You still need to report completion later:

```text
/done 2
```

If you forget to report completion by **5:00 AM the next day**, the day fails.

### Reporting in the wrong group

The bot tracks each Telegram group separately. If you use it in multiple groups, register and submit goals separately in each group.

### PMing the bot directly

The bot cannot run the challenge in a private chat because participants need to see the same goals, reminders, status, and leaderboard.

If you message the bot directly, it will give you a friendly intro and ask you to add **[@be_accountable_bot](https://t.me/be_accountable_bot)** to a group.

## Rules summary

- Use the bot in a Telegram group.
- Register once with `/register`.
- Submit exactly 3 goals by **10:00 AM Singapore time**.
- If everyone submits before the deadline, the goals summary posts immediately.
- If not everyone submits before the deadline, the 10:00 AM summary posts with submitted goals and tags only missing participants.
- Participants who register after 10:00 AM start from tomorrow and are not failed for that same day.
- Report completion with `/done 0`, `/done 1`, `/done 2`, or `/done 3`.
- After `/done 3`, send `/goals` that evening to draft the next day's goals; use `/confirmgoals` the next morning or replace them with fresh `/goals`.
- Complete **2/3 or 3/3** goals to pass.
- Missing goals or missing completion report counts as a fail.
- `/score` is a leaderboard ranked by fewest failed days.

## Need help?

In the Telegram group, send:

```text
/help
```

or:

```text
/rules
```

The bot will show the available commands and rules again.
