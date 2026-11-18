# Case: new_reserved_h

- Revision: 86

## Ticket details

age_89854: number (seconds)  
attempts_89854: number (count)  
urgent_89854: yes-no  
topic_89854: choice (billing,security,research)  

## Company rules

### policy_89854_1

- Order: 1
- Version: 1
- Location: new_policy/89854/paragraph/2

If urgent_89854 is yes and (topic_89854 is "security" or attempts_89854 is at least 8), send the ticket to "Priority_89854".

### policy_89854_0

- Order: 0
- Version: 1
- Location: new_policy/89854/paragraph/1

If topic_89854 is missing, send the ticket to "Manual_89854".

### policy_89854_2

- Order: 2
- Version: 1
- Location: new_policy/89854/paragraph/3

If age_89854 is at least 14 minutes and attempts_89854 is at least 4, send the ticket to "Escalation_89854".

### policy_89854_3

- Order: 3
- Version: 1
- Location: new_policy/89854/paragraph/4

For all remaining tickets, send the ticket to "Normal_89854".

## Specification

- Version: 6

### spec_89854_2

- Order: 2
- Company rule: policy_89854_2
- When: (age_89854 is at least 840 seconds and attempts_89854 is at least 4)
- Route: Escalation_89854

### spec_89854_3

- Order: 3
- Company rule: policy_89854_3
- When: always
- Route: Normal_89854

### spec_89854_0

- Order: 0
- Company rule: policy_89854_0
- When: topic_89854 is missing
- Route: Manual_89854

### spec_89854_1

- Order: 1
- Company rule: policy_89854_1
- When: (urgent_89854 is true and (topic_89854 is "security" or attempts_89854 is at least 8))
- Route: Priority_89854

## Workflow

- Version: 4
- Start: check_topic

### check_topic

- Company rule: policy_89854_0
- Code: router
- When: topic_89854 is missing
- Yes: out_manual
- No: check_priority

### check_priority

- Company rule: policy_89854_1
- When: (urgent_89854 is true and (topic_89854 is "security" or attempts_89854 is at least 8))
- Yes: out_priority
- No: check_age

### check_age

- Company rule: policy_89854_2
- When: (age_89854 is at least 840 seconds and attempts_89854 is at least 4)
- Yes: out_escalation
- No: out_normal

### out_manual

- Route: Manual_89854

### out_priority

- Route: Priority_89854

### out_escalation

- Route: Escalation_89854

### out_normal

- Route: Normal_89854

## Python

### router

- Version: 7

```python
def route(ticket):
    if ticket.get("topic_89854") is None:
        return "Manual_89854"
    if ticket.get("urgent_89854") == True and (ticket.get("topic_89854") == "security" or (ticket.get("attempts_89854") is not None and ticket.get("attempts_89854") >= 8)):
        return "Priority_89854"
    if ticket.get("age_89854") is not None and ticket.get("age_89854") >= 840 and ticket.get("attempts_89854") is not None and ticket.get("attempts_89854") >= 4:
        return "Escalation_89854"
    return "Normal_89854"
```

## Approvals

### approval_89854

- Company rule: policy_89854_2
- Status: approved
- Base version: 1
- Version: 2
- Sequence: 1
- From revision: 86
- To revision: 86

If age_89854 is at least 12 minutes and attempts_89854 is at least 4, send the ticket to "Escalation_89854".

### rejected_89854

- Company rule: policy_89854_2
- Status: rejected
- Base version: 1
- Version: 2
- Sequence: 1
- From revision: 86
- To revision: 86

If age_89854 is at least 12 minutes and attempts_89854 is at least 4, send the ticket to "Escalation_89854".


## Example tickets

### Example 1

topic_89854: billing  
urgent_89854: no  
age_89854: 840  
attempts_89854: 4  

### Example 2

urgent_89854: yes  
attempts_89854: 8  
age_89854: 840  

