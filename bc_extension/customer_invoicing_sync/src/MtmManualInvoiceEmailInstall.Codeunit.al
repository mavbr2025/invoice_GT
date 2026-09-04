codeunit 71017 "MTM Manual Inv Email Install"
{
    Subtype = Install;

    trigger OnInstallAppPerCompany()
    var
        Setup: Record "MTM Manual Inv Email Setup";
        SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
    begin
        SetupMgt.EnsureSetup(Setup);
    end;
}
