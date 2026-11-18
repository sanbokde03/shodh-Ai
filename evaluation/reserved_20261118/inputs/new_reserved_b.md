# Case: new_reserved_b

- Revision: 43

## Ticket details

age_49227: number (seconds)  
attempts_49227: number (count)  
urgent_49227: yes-no  
topic_49227: choice (billing,security,research)  

## Company rules

### policy_49227_0

- Order: 0
- Version: 1
- Location: new_policy/49227/paragraph/1

If topic_49227 is missing, send the ticket to "Manual_49227".

### policy_49227_1

- Order: 1
- Version: 1
- Location: new_policy/49227/paragraph/2

If urgent_49227 is yes and (topic_49227 is "security" or attempts_49227 is at least 7), send the ticket to "Priority_49227".

### policy_49227_2

- Order: 2
- Version: 1
- Location: new_policy/49227/paragraph/3

If age_49227 is at least 19 minutes and attempts_49227 is at least 2, send the ticket to "Escalation_49227".

### policy_49227_3

- Order: 3
- Version: 1
- Location: new_policy/49227/paragraph/4

For all remaining tickets, send the ticket to "Normal_49227".

## Specification

- Version: 7

### spec_49227_0

- Order: 0
- Company rule: policy_49227_0
- When: topic_49227 is missing
- Route: Manual_49227

### spec_49227_3

- Order: 3
- Company rule: policy_49227_3
- When: always
- Route: Normal_49227

### spec_49227_1

- Order: 1
- Company rule: policy_49227_1
- When: (urgent_49227 is true and (topic_49227 is "security" or attempts_49227 is at least 7))
- Route: Priority_49227

### spec_49227_2

- Order: 2
- Company rule: policy_49227_2
- When: (age_49227 is at least 960 seconds and attempts_49227 is at least 2)
- Route: Escalation_49227

## Workflow

- Version: 6
- Start: check_topic

### check_topic

- Company rule: policy_49227_0
- Code: router
- When: topic_49227 is missing
- Yes: out_manual
- No: check_priority

### check_priority

- Company rule: policy_49227_1
- When: (urgent_49227 is true and (topic_49227 is "security" or attempts_49227 is at least 7))
- Yes: out_priority
- No: check_age

### check_age

- Company rule: policy_49227_2
- When: (age_49227 is at least 960 seconds and attempts_49227 is at least 2)
- Yes: out_escalation
- No: out_normal

### out_manual

- Route: Manual_49227

### out_priority

- Route: Priority_49227

### out_escalation

- Route: Escalation_49227

### out_normal

- Route: Normal_49227

## Python

### router

- Version: 2

```python
def route(ticket):
    if ticket.get("topic_49227") is None:
        return "Manual_49227"
    if ticket.get("urgent_49227") == True and (ticket.get("topic_49227") == "security" or (ticket.get("attempts_49227") is not None and ticket.get("attempts_49227") >= 7)):
        return "Priority_49227"
    if ticket.get("age_49227") is not None and ticket.get("age_49227") >= 960 and ticket.get("attempts_49227") is not None and ticket.get("attempts_49227") >= 2:
        return "Escalation_49227"
    return "Normal_49227"
```

## Approvals

### approval_49227

- Company rule: policy_49227_2
- Status: approved
- Base version: 1
- Version: 2
- Sequence: 1
- From revision: 43
- To revision: 43

If age_49227 is at least 16 minutes and attempts_49227 is at least 2, send the ticket to "Escalation_49227".


## Example tickets

### Example 1

topic_49227: billing  
urgent_49227: no  
age_49227: 960  
attempts_49227: 2  

### Example 2

urgent_49227: yes  
attempts_49227: 7  
age_49227: 960  

