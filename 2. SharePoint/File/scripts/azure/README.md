Automation deployment helper
===========================

> **Attribution:** Taken from the [Microsoft AI-in-One Dashboard](https://github.com/microsoft/AI-in-One-Dashboard/tree/main/scripts/automation/azure) repository (MIT License, © Microsoft Corporation).

Quick notes:

- Deploy the Bicep template using the included `deploy.ps1` (uses Az PowerShell)

Commands:

```powershell
cd .\scripts\automation
.\deploy.ps1
.\upload-runbooks.ps1 -ResourceGroup '<rg>' -AutomationAccount '<namePrefix>-automation' -RunbooksPath .\runbooks
```


