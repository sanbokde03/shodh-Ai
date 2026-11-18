# Case: v3_a

- Revision: 74

## Ticket details

category: choice (billing,technical,research)  
urgent: yes-no  
waiting: number (minutes)

## Company rules

### policy_38181_3

- Order: 3
- Version: 1

For all remaining tickets, send the ticket to the normal queue.

### policy_13198_0

- Order: 0
- Version: 1

If category is missing, send the ticket for manual review.

### policy_40706_1

- Order: 1
- Version: 1

If the ticket is urgent, send the ticket to the priority queue.

### policy_36515_2

- Order: 2
- Version: 1

If waiting time is at least 50 minutes, escalate the ticket.

## Specification

- Version: 8

### S1

- Company rule: policy_13198_0
- When: category is missing
- Route: manual

### S2

- Company rule: policy_40706_1
- When: urgent is true
- Route: priority

### S3

- Company rule: policy_36515_2
- When: waiting is at least 50 minutes
- Route: escalation

### S4

- Company rule: policy_38181_3
- When: always
- Route: normal

## Workflow

- Version: 7
- Start: n1

### n1

- Company rule: policy_13198_0
- Code: main
- When: category is missing
- Yes: out_manual
- No: n2

### n2

- Company rule: policy_40706_1
- When: urgent is true
- Yes: out_priority
- No: n3

### n3

- Company rule: policy_36515_2
- When: waiting is at least 50 minutes
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

- Version: 6

```python
def route(ticket):
    if ticket.get("category") is None:
        return "manual"
    if ticket.get("urgent") == True:
        return "priority"
    if ticket.get("waiting") is not None and ticket.get("waiting") >= 50:
        return "escalation"
    return "normal"
```

## Approvals

None.
