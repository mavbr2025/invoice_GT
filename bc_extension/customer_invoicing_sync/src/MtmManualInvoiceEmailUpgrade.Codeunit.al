codeunit 71018 "MTM Manual Inv Email Upgrade"
{
    Subtype = Upgrade;

    trigger OnUpgradePerCompany()
    var
        Setup: Record "MTM Manual Inv Email Setup";
        SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
    begin
        SetupMgt.EnsureSetup(Setup);
    end;
}
