codeunit 71103 "MTM GT Invoice Std. Upgrade"
{
    Subtype = Upgrade;

    trigger OnUpgradePerCompany()
    var
        Setup: Codeunit "MTM GT Invoice Std. Setup";
    begin
        Setup.ApplyInvoiceLayoutRouting();
    end;
}
