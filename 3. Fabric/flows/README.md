# Product feedback OneLake landing flow

[`Copilot_ProductFeedback_Email_to_OneLake.json`](Copilot_ProductFeedback_Email_to_OneLake.json)
lands an emailed Microsoft 365 Copilot product-feedback CSV in `Files/product_feedback/`.
The export must already exist; this flow does not automate the admin portal export.

## Setup

1. Import the flow into Power Automate and configure its Outlook connection and email filter.
2. Set `OneLakeWorkspace`, `OneLakeLakehouse`, and `TargetFolder` (`Files/product_feedback`) to your target. Keep the folder aligned with the ingester's `SOURCE_DIR`.
3. Configure the OneLake HTTP authentication for the `https://storage.azure.com/` audience. The identity needs write access to the target Lakehouse. Store credentials securely; never embed a literal secret in a shared definition.
4. Land the CSV before running [`Copilot_ProductFeedback_Ingester.ipynb`](../notebooks/Copilot_ProductFeedback_Ingester.ipynb), which writes `user_feedback`.
5. Enable the pipeline's `EnableProductFeedback` branch and set the model's `Enable_ProductFeedback` parameter to `Include` when ready. Refresh the model only after its source branches succeed; see [pipeline setup](../pipelines/README.md#refresh-power-bi-from-the-pipeline).

The flow uses the OneLake DFS create/append/flush pattern. Use the ingester's default snapshot mode unless you deliberately manage duplicate files and append semantics.

## Archived consumption flows

The cost-consumption email and SharePoint flows and their guides now live in
[`archive/flows`](../archive/flows/COST-CONSUMPTION-SETUP.md).
The Copilot Studio extension and its PPAC credit-consumption flows are in
[`archive/extended`](../archive/extended/README.md).
These are archived reference assets, not part of the active feedback setup.
