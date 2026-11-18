# Case: new_reserved_a

- Revision: 75

## Ticket details

age_76682: number (seconds)  
attempts_76682: number (count)  
urgent_76682: yes-no  
topic_76682: choice (billing,security,research)  

## Company rules

### policy_76682_0

- Order: 0
- Version: 1
- Location: new_policy/76682/paragraph/1

If topic_76682 is missing, send the ticket to "Manual_76682".

### policy_76682_1

- Order: 1
- Version: 1
- Location: new_policy/76682/paragraph/2

If urgent_76682 is yes and (topic_76682 is "security" or attempts_76682 is at least 7), send the ticket to "Priority_76682".

### policy_76682_3

- Order: 3
- Version: 1
- Location: new_policy/76682/paragraph/4

For all remaining tickets, send the ticket to "Normal_76682".

### policy_76682_2

- Order: 2
- Version: 1
- Location: new_policy/76682/paragraph/3

If not (age_76682 is less than 22 minutes or age_76682 is missing) and attempts_76682 is at least 3, send the ticket to "Escalation_76682".

## Specification

- Version: 5

### spec_76682_3

- Order: 3
- Company rule: policy_76682_3
- When: always
- Route: Normal_76682

### spec_76682_0

- Order: 0
- Company rule: policy_76682_0
- When: topic_76682 is missing
- Route: Manual_76682

### spec_76682_2

- Order: 2
- Company rule: policy_76682_2
- When: (age_76682 is at least 1320 seconds and attempts_76682 is at least 3)
- Route: Escalation_76682

### spec_76682_1

- Order: 1
- Company rule: policy_76682_1
- When: (urgent_76682 is true and (topic_76682 is "security" or attempts_76682 is at least 7))
- Route: Priority_76682

## Workflow

- Version: 7
- Start: check_topic

### check_topic

- Company rule: policy_76682_0
- Code: router
- When: topic_76682 is missing
- Yes: out_manual
- No: check_priority

### check_priority

- Company rule: policy_76682_1
- When: (urgent_76682 is true and (topic_76682 is "security" or attempts_76682 is at least 7))
- Yes: out_priority
- No: check_age

### check_age

- Company rule: policy_76682_2
- When: (age_76682 is at least 1320 seconds and attempts_76682 is at least 3)
- Yes: out_escalation
- No: out_normal

### out_manual

- Route: Manual_76682

### out_priority

- Route: Priority_76682

### out_escalation

- Route: Escalation_76682

### out_normal

- Route: Normal_76682

## Python

### router

- Version: 6

```python
def route(ticket):
    if ticket.get("topic_76682") is None:
        return "Manual_76682"
    if ticket.get("urgent_76682") == True and (ticket.get("topic_76682") == "security" or (ticket.get("attempts_76682") is not None and ticket.get("attempts_76682") >= 7)):
        return "Priority_76682"
    if ticket.get("age_76682") is not None and ticket.get("age_76682") >= 1320 and ticket.get("attempts_76682") is not None and ticket.get("attempts_76682") >= 3:
        return "Escalation_76682"
    return "Normal_76682"
```

## Approvals

### approval_76682

- Company rule: policy_76682_2
- Status: proposed
- Base version: 1
- Version: 2
- Sequence: 1
- From revision: 75
- To revision: 75

If age_76682 is at least 20 minutes and attempts_76682 is at least 3, send the ticket to "Escalation_76682".


## Example tickets

### Example 1

topic_76682: billing  
urgent_76682: no  
age_76682: 1320  
attempts_76682: 3  

### Example 2

urgent_76682: yes  
attempts_76682: 7  
age_76682: 1320  

