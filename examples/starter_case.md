# Case: starter_case

## Ticket details

waiting: number (minutes)

## Company rules

### wait_rule

Escalate tickets waiting 30 minutes or more.

### fallback

Send all remaining tickets to the normal queue.

## Specification

### planned_wait

- Company rule: wait_rule
- When: waiting is at least 30 minutes
- Route: escalation

### planned_default

- Company rule: fallback
- When: always
- Route: normal

## Workflow

- Start: check_wait

### check_wait

- Company rule: wait_rule
- Code: main
- When: waiting is at least 30 minutes
- Yes: escalate
- No: normal

### escalate

- Route: escalation

### normal

- Route: normal

## Python

### main

```python
def route(ticket):
    if ticket.get("waiting") is not None and ticket.get("waiting") >= 30:
        return "escalation"
    return "normal"
```

## Approvals

None.

## Example tickets

waiting: 30 minutes
