# Case: new_reserved_d

- Revision: 43

## Ticket details

age_19174: number (seconds)  
attempts_19174: number (count)  
urgent_19174: yes-no  
topic_19174: choice (billing,security,research)  

## Company rules

### policy_19174_0

- Order: 0
- Version: 1
- Location: new_policy/19174/paragraph/1

If topic_19174 is missing, send the ticket to "Manual_19174".

### policy_19174_3

- Order: 3
- Version: 1
- Location: new_policy/19174/paragraph/4

For all remaining tickets, send the ticket to "Normal_19174".

### policy_19174_2

- Order: 2
- Version: 1
- Location: new_policy/19174/paragraph/3

If age_19174 is at least 19 minutes and attempts_19174 is at least 3, send the ticket to "Escalation_19174".

### policy_19174_1

- Order: 1
- Version: 1
- Location: new_policy/19174/paragraph/2

If urgent_19174 is yes and (topic_19174 is "security" or attempts_19174 is at least 7), send the ticket to "Priority_19174".

## Specification

- Version: 3

### spec_19174_1

- Order: 1
- Company rule: policy_19174_1
- When: (urgent_19174 is true and (topic_19174 is "security" or attempts_19174 is at least 7))
- Route: Priority_19174

### spec_19174_3

- Order: 3
- Company rule: policy_19174_3
- When: always
- Route: Normal_19174

### spec_19174_0

- Order: 0
- Company rule: policy_19174_0
- When: topic_19174 is missing
- Route: Manual_19174

### spec_19174_2

- Order: 2
- Company rule: policy_19174_2
- When: (age_19174 is at least 1140 seconds and attempts_19174 is at least 3)
- Route: Escalation_19174

## Workflow

- Version: 3
- Start: check_priority

### check_topic

- Company rule: policy_19174_0
- When: topic_19174 is missing
- Yes: out_manual
- No: check_age

### check_priority

- Company rule: policy_19174_1
- Code: router
- When: (urgent_19174 is true and (topic_19174 is "security" or attempts_19174 is at least 7))
- Yes: out_priority
- No: check_topic

### check_age

- Company rule: policy_19174_2
- When: (age_19174 is at least 1140 seconds and attempts_19174 is at least 3)
- Yes: out_escalation
- No: out_normal

### out_manual

- Route: Manual_19174

### out_priority

- Route: Priority_19174

### out_escalation

- Route: Escalation_19174

### out_normal

- Route: Normal_19174

## Python

### router

- Version: 2

```python
def route(ticket):
    if ticket.get("topic_19174") is None:
        return "Manual_19174"
    if ticket.get("urgent_19174") == True and (ticket.get("topic_19174") == "security" or (ticket.get("attempts_19174") is not None and ticket.get("attempts_19174") >= 7)):
        return "Priority_19174"
    if ticket.get("age_19174") is not None and ticket.get("age_19174") >= 1140 and ticket.get("attempts_19174") is not None and ticket.get("attempts_19174") >= 3:
        return "Escalation_19174"
    return "Normal_19174"
```

## Approvals

None.

## Example tickets

### Example 1

topic_19174: billing  
urgent_19174: no  
age_19174: 1140  
attempts_19174: 3  

### Example 2

urgent_19174: yes  
attempts_19174: 7  
age_19174: 1140  

