# Accountability Bot

A friendly Telegram bot that helps a 2-person group stay accountable with daily goals, reminders, status updates, and month-end settlement.

Use the bot here: **[@be_accountable_bot](https://t.me/be_accountable_bot)**

## What the bot does

`@be_accountable_bot` runs a simple daily accountability challenge:

1. Everyone submits **exactly 3 goals** in the morning.
2. Everyone reports how many goals they completed at night.
3. The bot tracks who passed or failed each day.
4. At month end, the person with more failed days pays the other person based on the settlement rule.

It is designed for a Telegram group with **2 people**, so both players can see the goals, reminders, and status updates together.

It does **not** run in private messages. If you PM the bot, it will explain that it needs to be added to a 2-person group first.

## Quick start

### 1. Add the bot to your Telegram group

Create or choose a Telegram group with exactly **2 people**, then add **[@be_accountable_bot](https://t.me/be_accountable_bot)** to that group.

Once the bot joins, it will introduce itself and explain the basic flow.

### 2. Register yourself

Each participant should send this once in the group:

```text
/register
```

Example response:

```text
Registered Ernest ✅

Current players
1. Ernest
2. Cyril
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
| 8:00 AM | Morning reminder to submit goals |
| 9:30 AM | Reminder tagging only people who have not submitted goals |
| 10:00 AM | Goal deadline |
| 8:00 PM | Completion reminder |
| 10:00 PM | Final completion reminder |
| 5:00 AM next day | Completion deadline |

If you do not submit goals by **10:00 AM**, the day counts as failed.

If you do not report completion by **5:00 AM the next day**, the day counts as failed.

## Commands

| Command | What it does | Example |
|---|---|---|
| `/register` | Join the accountability challenge | `/register` |
| `/goals` | Submit exactly 3 goals for today | `/goals` followed by 3 lines |
| `/done 0` | Report that you completed 0 goals | `/done 0` |
| `/done 1` | Report that you completed 1 goal | `/done 1` |
| `/done 2` | Report that you completed 2 goals | `/done 2` |
| `/done 3` | Report that you completed all 3 goals | `/done 3` |
| `/today` | Show today's goals and status | `/today` |
| `/score` | Show current month standings and settlement | `/score` |
| `/summary` | Same as `/score` | `/summary` |
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
- 3x leetcode
- gym
- read
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
Daily Status — 2026-07-09

cyril
Status: ⏳ pending — not reported
Goals
1. settle course registration
2. chest and back
3. read

Ernest
Status: ✅ pass — 2/3
Goals
1. 3x leetcode
2. gym
3. read
```

Status meanings:

| Status | Meaning |
|---|---|
| ⏳ pending | The day is still in progress |
| ✅ pass | Completed at least 2 out of 3 goals |
| ❌ fail | Missed goals, missed completion report, or completed fewer than 2 goals |

## Month-end settlement

Use:

```text
/score
```

The bot counts failed days for the current month.

Settlement rule:

```text
Person with more failed days pays the other person $5 × difference.
```

Examples:

| Ernest failed days | Cyril failed days | Settlement |
|---:|---:|---|
| 3 | 1 | Ernest pays Cyril $10 |
| 2 | 5 | Cyril pays Ernest $15 |
| 4 | 4 | Tie — nobody pays |

This is a **net settlement**, so if both people fail equally often, nobody pays.

## Quote of the day

When everyone has submitted their goals, the bot sends a group summary with today's goals and a **Quote of the Day**.

The quote comes from an external quote API. If the quote service is temporarily unavailable, the bot will still send the goals summary.

## Friendly tips

- Submit your goals early so you do not get tagged by the 9:30 AM reminder.
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

The bot cannot run the challenge in a private chat because both players need to see the same goals, reminders, status, and settlement.

If you message the bot directly, it will give you a friendly intro and ask you to add **[@be_accountable_bot](https://t.me/be_accountable_bot)** to a group with **2 people**.

## Rules summary

- Use the bot in a Telegram group with **2 people**.
- Register once with `/register`.
- Submit exactly 3 goals by **10:00 AM Singapore time**.
- Report completion with `/done 0`, `/done 1`, `/done 2`, or `/done 3`.
- Complete **2/3 or 3/3** goals to pass.
- Missing goals or missing completion report counts as a fail.
- Month-end settlement is `$5 × failed-day difference`.
- If failed days are tied, nobody pays.

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
