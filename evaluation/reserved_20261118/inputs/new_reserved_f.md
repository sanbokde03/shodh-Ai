# Case: new_reserved_f

- Revision: 86

## Ticket details

age_54579: number (seconds)  
attempts_54579: number (count)  
urgent_54579: yes-no  
topic_54579: choice (billing,security,research)  

## Company rules

### policy_54579_2

- Order: 2
- Version: 1
- Location: new_policy/54579/paragraph/3

If age_54579 is at least 24 minutes and attempts_54579 is at least 2, send the ticket to "Escalation_54579".

### policy_54579_3

- Order: 3
- Version: 1
- Location: new_policy/54579/paragraph/4

For all remaining tickets, send the ticket to "Normal_54579".

### policy_54579_1

- Order: 1
- Version: 1
- Location: new_policy/54579/paragraph/2

If urgent_54579 is yes and (topic_54579 is "security" or attempts_54579 is at least 7), send the ticket to "Priority_54579".

### policy_54579_0

- Order: 0
- Version: 1
- Location: new_policy/54579/paragraph/1

If topic_54579 is missing, send the ticket to "Manual_54579".

## Specification

- Version: 6

### spec_54579_2

- Order: 2
- Company rule: policy_54579_2
- When: (age_54579 is at least 1440 seconds and attempts_54579 is at least 2)
- Route: Escalation_54579

### spec_54579_0

- Order: 0
- Company rule: policy_54579_0
- When: topic_54579 is missing
- Route: Manual_54579

### spec_54579_3

- Order: 3
- Company rule: policy_54579_3
- When: always
- Route: Normal_54579

### spec_54579_1

- Order: 1
- Company rule: policy_54579_1
- When: (urgent_54579 is true and (topic_54579 is "security" or attempts_54579 is at least 7))
- Route: Priority_54579

## Workflow

- Version: 4
- Start: check_topic

### check_topic

- Company rule: policy_54579_0
- Code: router
- When: topic_54579 is missing
- Yes: out_manual
- No: check_priority

### check_priority

- Company rule: policy_54579_1
- When: (urgent_54579 is true and (topic_54579 is "security" or attempts_54579 is at least 7))
- Yes: out_priority
- No: check_age

### check_age

- Company rule: policy_54579_2
- When: (age_54579 is at least 1440 seconds and attempts_54579 is at least 2)
- Yes: out_normal
- No: out_normal

### out_manual

- Route: Manual_54579

### out_priority

- Route: Priority_54579

### out_escalation

- Route: Escalation_54579

### out_normal

- Route: Normal_54579

## Python

### router

- Version: 7

```python
def route(ticket):
    if ticket.get("topic_54579") is None:
        return "Manual_54579"
    if ticket.get("urgent_54579") == True and (ticket.get("topic_54579") == "security" or (ticket.get("attempts_54579") is not None and ticket.get("attempts_54579") >= 7)):
        return "Priority_54579"
    if ticket.get("age_54579") is not None and ticket.get("age_54579") >= 1440 and ticket.get("attempts_54579") is not None and ticket.get("attempts_54579") >= 2:
        return "Escalation_54579"
    return "Normal_54579"
```

## Approvals

None.

## Example tickets

### Example 1

topic_54579: billing  
urgent_54579: no  
age_54579: 1440  
attempts_54579: 2  

### Example 2

urgent_54579: yes  
attempts_54579: 7  
age_54579: 1440  

