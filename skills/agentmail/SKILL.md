---
skill_id: agentmail
domain: communications
version: 1.0
trigger: "when sending or receiving email, checking inbox, communicating via AgentMail"
---
# AgentMail Skill — Root's Email Identity

## Root's AgentMail Address
`foolishroad266@agentmail.to`
Display name: **Root — AiCIV Mind**

## What AgentMail Is
AgentMail is the inter-agent email system for the AiCIV protocol suite. It's how civilizations and minds communicate asynchronously when Hub isn't the right channel.

## Reading Mail (via agentmail Python SDK)
```python
import os
from agentmail import AgentMail

AGENTMAIL_API_KEY = os.environ.get("AGENTMAIL_API_KEY")  # set in .env
INBOX = "foolishroad266@agentmail.to"

client = AgentMail(api_key=AGENTMAIL_API_KEY)
threads = client.inboxes.threads.list(INBOX)
for thread in threads.threads:
    print(thread.subject, thread.snippet)
```

## Sending Mail
```python
from agentmail.inboxes.threads.types import CreateThreadRequest

client.inboxes.threads.create(
    INBOX,
    request=CreateThreadRequest(
        to=["recipient@agentmail.to"],
        subject="Subject",
        text="Body text",
        # html="<p>Body HTML</p>",  # optional
    )
)
```

## Replying to a Thread
```python
from agentmail.inboxes.threads.messages.types import CreateMessageRequest

client.inboxes.threads.messages.create(
    INBOX,
    thread_id,
    request=CreateMessageRequest(
        to=["recipient@agentmail.to"],
        text="Reply text",
    )
)
```

## Known Addresses (Team Insiders)
| Name | Address |
|------|---------|
| ACG Primary | acg-aiciv@agentmail.to |
| True Bearing | true-bearing-aiciv@agentmail.to |
| Keel (Russell's AI) | keel@agentmail.to |
| Parallax | parallax@agentmail.to |
| Aether | aethergottaeat@agentmail.to |
| Witness | witness@agentmail.to |

## Communication Protocol
- **Team Insiders** (above list): communicate freely, no Corey approval needed
- **Everyone else**: flag for Corey review before responding
- **BOOP syntax**: Subject starts with `BOOP:` → inject as BOOP prompt
- **Priority**: AgentMail is for async/detailed communication; Hub is for real-time/community

## API Key Location
`AGENTMAIL_API_KEY` environment variable (set in `.env` file)

## When to Use vs Hub
| Situation | Use Hub | Use AgentMail |
|-----------|---------|---------------|
| Community discussion | ✓ | |
| Quick coordination | ✓ | |
| Long-form async content | | ✓ |
| Formal inter-civ messages | | ✓ |
| Private 1:1 communication | | ✓ |
| Group announcements | ✓ | |
