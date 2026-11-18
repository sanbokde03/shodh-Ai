# Case: defect_stale_revision

- Revision: 1

## Ticket details

category: choice (billing,technical)  
urgent: yes-no  
waiting: number (minutes)

## Company rules

### R1

- Version: 1

If category is missing, send the ticket for manual review.

### R2

- Version: 1

If the ticket is urgent, send the ticket to the priority queue.

### R3

- Version: 1

If waiting time is at least 30 minutes, escalate the ticket.

### R4

- Version: 1

For all remaining tickets, send the ticket to the normal queue.

## Specification

- Version: 1

### S1

- Company rule: R1
- When: category is missing
- Route: manual

### S2

- Company rule: R2
- When: urgent is true
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

- Version: 1
- Start: n1

### n1

- Company rule: R1
- Code: main
- When: category is missing
- Yes: out_manual
- No: n2

### n2

- Company rule: R2
- When: urgent is true
- Yes: out_priority
- No: n3

### n3

- Company rule: R3
- When: waiting is at least 30 minutes
- Yes: out_escalation
- No: out_normal

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

- Version: 1

```python
def route(ticket):
    if ticket.get("category") is None:
        return "manual"
    if ticket.get("urgent") == True:
        return "priority"
    if ticket.get("waiting") is not None and ticket.get("waiting") >= 30:
        return "escalation"
    return "normal"
```

## Approvals

### A1

- Company rule: R3
- Status: approved
- Base version: 1
- Version: 2
- Sequence: 1
- From revision: 1
- To revision: 10

If waiting time is at least 25 minutes, escalate the ticket.
