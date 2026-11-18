# Case: new_reserved_c

- Revision: 89

## Ticket details

age_95725: number (seconds)  
attempts_95725: number (count)  
urgent_95725: yes-no  
topic_95725: choice (billing,security,research)  

## Company rules

### policy_95725_3

- Order: 3
- Version: 1
- Location: new_policy/95725/paragraph/4

For all remaining tickets, send the ticket to "Normal_95725".

### policy_95725_2

- Order: 2
- Version: 1
- Location: new_policy/95725/paragraph/3

If age_95725 is at least 26 minutes and attempts_95725 is at least 2, send the ticket to "Escalation_95725".

### policy_95725_1

- Order: 1
- Version: 1
- Location: new_policy/95725/paragraph/2

If urgent_95725 is yes and (topic_95725 is "security" or attempts_95725 is at least 8), send the ticket to "Priority_95725".

### policy_95725_0

- Order: 0
- Version: 1
- Location: new_policy/95725/paragraph/1

If topic_95725 is missing, send the ticket to "Manual_95725".

## Specification

- Version: 3

### spec_95725_1

- Order: 1
- Company rule: policy_95725_1
- When: (urgent_95725 is true and (topic_95725 is "security" or attempts_95725 is at least 8))
- Route: Priority_95725

### spec_95725_2

- Order: 2
- Company rule: policy_95725_2
- When: (age_95725 is at least 1560 seconds and attempts_95725 is at least 2)
- Route: Escalation_95725

### spec_95725_0

- Order: 0
- Company rule: policy_95725_0
- When: topic_95725 is missing
- Route: Manual_95725

### spec_95725_3

- Order: 3
- Company rule: policy_95725_3
- When: always
- Route: Normal_95725

## Workflow

- Version: 5
- Start: check_topic

### check_topic

- Company rule: policy_95725_0
- Code: router
- When: topic_95725 is missing
- Yes: out_manual
- No: check_priority

### check_priority

- Company rule: policy_95725_1
- When: (urgent_95725 is true and (topic_95725 is "security" or attempts_95725 is at least 8))
- Yes: out_priority
- No: check_age

### check_age

- Company rule: policy_95725_2
- When: (age_95725 is more than 1560 seconds and attempts_95725 is at least 2)
- Yes: out_escalation
- No: out_normal

### out_manual

- Route: Manual_95725

### out_priority

- Route: Priority_95725

### out_escalation

- Route: Escalation_95725

### out_normal

- Route: Normal_95725

## Python

### router

- Version: 2

```python
def route(ticket):
    if ticket.get("topic_95725") is None:
        return "Manual_95725"
    if ticket.get("urgent_95725") == True and (ticket.get("topic_95725") == "security" or (ticket.get("attempts_95725") is not None and ticket.get("attempts_95725") >= 8)):
        return "Priority_95725"
    if ticket.get("age_95725") is not None and ticket.get("age_95725") >= 1560 and ticket.get("attempts_95725") is not None and ticket.get("attempts_95725") >= 2:
        return "Escalation_95725"
    return "Normal_95725"
```

## Approvals

None.

## Example tickets

### Example 1

topic_95725: billing  
urgent_95725: no  
age_95725: 1560  
attempts_95725: 2  

### Example 2

urgent_95725: yes  
attempts_95725: 8  
age_95725: 1560  

