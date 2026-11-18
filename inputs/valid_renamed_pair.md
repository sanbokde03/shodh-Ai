# Case: valid_renamed_pair

## Ticket details

category: choice (billing,technical)  
urgent: yes-no  
waiting: number (minutes)

## Company rules

### policy_94

- Order: 3

For all remaining tickets, send the ticket to the normal queue.

### policy_93

- Order: 2

If waiting time is at least 30 minutes, escalate the ticket.

### policy_92

- Order: 1

If the ticket is urgent, send the ticket to the priority queue.

### policy_91

- Order: 0

If category is missing, send the ticket for manual review.

## Specification

### S4

- Order: 3
- Company rule: policy_94
- When: always
- Route: normal

### S1

- Order: 0
- Company rule: policy_91
- When: category is missing
- Route: manual

### S3

- Company rule: policy_93
- When: waiting is at least 30 minutes
- Route: escalation

### S2

- Order: 1
- Company rule: policy_92
- When: urgent is true
- Route: priority

## Workflow

- Start: n1

### out_manual

- Route: manual

### n1

- Company rule: policy_91
- Code: main
- When: category is missing
- Yes: out_manual
- No: n2

### out_normal

- Route: normal

### out_escalation

- Route: escalation

### out_priority

- Route: priority

### n3

- Company rule: policy_93
- When: waiting is at least 30 minutes
- Yes: out_escalation
- No: out_normal

### n2

- Company rule: policy_92
- When: urgent is true
- Yes: out_priority
- No: n3

## Python

### main

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

None.
