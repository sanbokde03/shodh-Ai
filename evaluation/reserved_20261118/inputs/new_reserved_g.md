# Case: new_reserved_g

- Revision: 75

## Ticket details

age_89567: number (seconds)  
attempts_89567: number (count)  
urgent_89567: yes-no  
topic_89567: choice (billing,security,research)  

## Company rules

### policy_89567_3

- Order: 3
- Version: 1
- Location: new_policy/89567/paragraph/4

For all remaining tickets, send the ticket to "Normal_89567".

### policy_89567_0

- Order: 0
- Version: 1
- Location: new_policy/89567/paragraph/1

If topic_89567 is missing, send the ticket to "Manual_89567".

### policy_89567_2

- Order: 2
- Version: 1
- Location: new_policy/89567/paragraph/3

If age_89567 is too long and attempts_89567 is at least 2, send the ticket to "Escalation_89567".

### policy_89567_1

- Order: 1
- Version: 1
- Location: new_policy/89567/paragraph/2

If urgent_89567 is yes and (topic_89567 is "security" or attempts_89567 is at least 8), send the ticket to "Priority_89567".

## Specification

- Version: 6

### spec_89567_3

- Order: 3
- Company rule: policy_89567_3
- When: always
- Route: Normal_89567

### spec_89567_1

- Order: 1
- Company rule: policy_89567_1
- When: (urgent_89567 is true and (topic_89567 is "security" or attempts_89567 is at least 8))
- Route: Priority_89567

### spec_89567_0

- Order: 0
- Company rule: policy_89567_0
- When: topic_89567 is missing
- Route: Manual_89567

### spec_89567_2

- Order: 2
- Company rule: policy_89567_2
- When: (age_89567 is at least 1500 seconds and attempts_89567 is at least 2)
- Route: Escalation_89567

## Workflow

- Version: 5
- Start: check_topic

### check_topic

- Company rule: policy_89567_0
- Code: router
- When: topic_89567 is missing
- Yes: out_manual
- No: check_priority

### check_priority

- Company rule: policy_89567_1
- When: (urgent_89567 is true and (topic_89567 is "security" or attempts_89567 is at least 8))
- Yes: out_priority
- No: check_age

### check_age

- Company rule: policy_89567_2
- When: (age_89567 is at least 1500 seconds and attempts_89567 is at least 2)
- Yes: out_escalation
- No: out_normal

### out_manual

- Route: Manual_89567

### out_priority

- Route: Priority_89567

### out_escalation

- Route: Escalation_89567

### out_normal

- Route: Normal_89567

## Python

### router

- Version: 2

```python
def route(ticket):
    if ticket.get("topic_89567") is None:
        return "Manual_89567"
    if ticket.get("urgent_89567") == True and (ticket.get("topic_89567") == "security" or (ticket.get("attempts_89567") is not None and ticket.get("attempts_89567") >= 8)):
        return "Priority_89567"
    if ticket.get("age_89567") is not None and ticket.get("age_89567") >= 1500 and ticket.get("attempts_89567") is not None and ticket.get("attempts_89567") >= 2:
        return "Escalation_89567"
    return "Normal_89567"
```

## Approvals

None.

## Example tickets

### Example 1

topic_89567: billing  
urgent_89567: no  
age_89567: 1500  
attempts_89567: 2  

### Example 2

urgent_89567: yes  
attempts_89567: 8  
age_89567: 1500  

