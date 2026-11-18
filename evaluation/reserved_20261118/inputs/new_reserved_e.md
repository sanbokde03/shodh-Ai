# Case: new_reserved_e

- Revision: 73

## Ticket details

age_71416: number (seconds)  
attempts_71416: number (count)  
urgent_71416: yes-no  
topic_71416: choice (billing,security,research)  

## Company rules

### policy_71416_0

- Order: 0
- Version: 1
- Location: new_policy/71416/paragraph/1

If topic_71416 is missing, send the ticket to "Manual_71416".

### policy_71416_3

- Order: 3
- Version: 1
- Location: new_policy/71416/paragraph/4

For all remaining tickets, send the ticket to "Normal_71416".

### policy_71416_2

- Order: 2
- Version: 1
- Location: new_policy/71416/paragraph/3

If age_71416 is at least 23 minutes and attempts_71416 is at least 3, send the ticket to "Escalation_71416".

### policy_71416_1

- Order: 1
- Version: 1
- Location: new_policy/71416/paragraph/2

If urgent_71416 is yes and (topic_71416 is "security" or attempts_71416 is at least 8), send the ticket to "Priority_71416".

## Specification

- Version: 7

### spec_71416_3

- Order: 3
- Company rule: policy_71416_3
- When: always
- Route: Normal_71416

### spec_71416_1

- Order: 1
- Company rule: policy_71416_1
- When: (urgent_71416 is true and (topic_71416 is "security" or attempts_71416 is at least 8))
- Route: Priority_71416

### spec_71416_0

- Order: 0
- Company rule: policy_71416_0
- When: topic_71416 is missing
- Route: Manual_71416

### spec_71416_2

- Order: 2
- Company rule: policy_71416_2
- When: (age_71416 is at least 1380 seconds and attempts_71416 is at least 3)
- Route: Escalation_71416

## Workflow

- Version: 3
- Start: check_topic

### check_topic

- Company rule: policy_71416_0
- Code: router
- When: topic_71416 is missing
- Yes: out_manual
- No: check_priority

### check_priority

- Company rule: policy_71416_1
- When: (urgent_71416 is true and (topic_71416 is "security" or attempts_71416 is at least 8))
- Yes: out_priority
- No: check_age

### check_age

- Company rule: policy_71416_2
- When: (age_71416 is at least 1380 seconds and attempts_71416 is at least 3)
- Yes: out_escalation
- No: out_normal

### out_manual

- Route: Manual_71416

### out_priority

- Route: Priority_71416

### out_escalation

- Route: Escalation_71416

### out_normal

- Route: Normal_71416

## Python

### router

- Version: 6

```python
def route(ticket):
    if ticket.get("topic_71416") is None:
        return "Manual_71416"
    if ticket["urgent_71416"] == True and (ticket.get("topic_71416") == "security" or (ticket.get("attempts_71416") is not None and ticket.get("attempts_71416") >= 8)):
        return "Priority_71416"
    if ticket.get("age_71416") is not None and ticket.get("age_71416") >= 1380 and ticket.get("attempts_71416") is not None and ticket.get("attempts_71416") >= 3:
        return "Escalation_71416"
    return "Normal_71416"
```

## Approvals

None.

## Example tickets

### Example 1

topic_71416: billing  
urgent_71416: no  
age_71416: 1380  
attempts_71416: 3  

### Example 2

urgent_71416: yes  
attempts_71416: 8  
age_71416: 1380  

