# Case: v3_c

- Revision: 62

## Ticket details

category: choice (billing,technical,research)  
urgent: yes-no  
waiting: number (minutes)

## Company rules

### policy_89907_3

- Order: 3
- Version: 1

For all remaining tickets, send the ticket to the normal queue.

### policy_86792_0

- Order: 0
- Version: 1

If category is missing, send the ticket for manual review.

### policy_27673_2

- Version: 1

If waiting time is at least 75 minutes, escalate the ticket.

### policy_81034_1

- Order: 1
- Version: 1

If the ticket is urgent, send the ticket to the priority queue.

## Specification

- Version: 6

### S1

- Company rule: policy_86792_0
- When: category is missing
- Route: manual

### S2

- Company rule: policy_81034_1
- When: urgent is true
- Route: priority

### S3

- Company rule: policy_27673_2
- When: waiting is at least 75 minutes
- Route: escalation

### S4

- Company rule: policy_89907_3
- When: always
- Route: normal

## Workflow

- Version: 11
- Start: n1

### n1

- Company rule: policy_86792_0
- Code: main
- When: category is missing
- Yes: out_manual
- No: n2

### n2

- Company rule: policy_81034_1
- When: urgent is true
- Yes: out_priority
- No: n3

### n3

- Company rule: policy_27673_2
- When: waiting is at least 75 minutes
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

- Version: 5

```python
def route(ticket):
    if ticket.get("category") is None:
        return "manual"
    if ticket.get("urgent") == True:
        return "priority"
    if ticket.get("waiting") is not None and ticket.get("waiting") >= 75:
        return "escalation"
    return "normal"
```

## Approvals

### decision_a

- Company rule: policy_27673_2
- Status: approved
- Base version: 1
- Version: 2
- Sequence: 1
- From revision: 62
- To revision: 62

If waiting time is at least 75 minutes, escalate the ticket.

### decision_b

- Company rule: policy_27673_2
- Status: rejected
- Base version: 1
- Version: 2
- Sequence: 1
- From revision: 62
- To revision: 62

If waiting time is at least 75 minutes, escalate the ticket.
