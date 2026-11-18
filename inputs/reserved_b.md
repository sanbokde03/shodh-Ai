# Case: reserved_b

## Ticket details

category: choice (billing,technical)  
urgent: yes-no  
waiting: number (minutes)

## Company rules

### R1

If category is missing, send the ticket for manual review.

### R2

If (the ticket is urgent and category is "technical"), send the ticket to the priority queue.

### R3

If waiting time is at least 30 minutes, escalate the ticket.

### R4

For all remaining tickets, send the ticket to the normal queue.

## Specification

### S1

- Company rule: R1
- When: category is missing
- Route: manual

### S2

- Company rule: R2
- When: (urgent is true and category is "technical")
- Route: priority

### S3

- Company rule: R3
- When: waiting is at least 30 minutes
- Route: escalation

### S4

- Company rule: R4
- When: always
- Route: normal

## Workflow

- Start: n3

### n1

- Company rule: R1
- When: category is missing
- Yes: out_manual
- No: n2

### n2

- Company rule: R2
- When: (urgent is true and category is "technical")
- Yes: out_priority
- No: out_normal

### n3

- Company rule: R3
- Code: main
- When: waiting is at least 30 minutes
- Yes: out_escalation
- No: n1

### out_manual

- Route: manual

### out_priority

- Route: priority

### out_escalation

- Route: escalation

### out_normal

- Route: normal

## Python

### main

```python
def route(ticket):
    if ticket.get("category") is None:
        return "manual"
    if ticket.get("urgent") == True and ticket.get("category") == "technical":
        return "priority"
    if ticket.get("waiting") is not None and ticket.get("waiting") >= 30:
        return "escalation"
    return "normal"
```

## Approvals

None.
