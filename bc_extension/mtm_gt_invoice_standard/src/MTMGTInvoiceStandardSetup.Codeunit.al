codeunit 71101 "MTM GT Invoice Std. Setup"
{
    Subtype = Install;

    var
        LayoutNameLbl: Label 'MTMGTInvoiceStandard202606OnePage', Locked = true;
        LayoutCaptionLbl: Label 'MTM GT Invoice Standard 2026-06 One Page', Locked = true;

    trigger OnInstallAppPerCompany()
    begin
        ApplyInvoiceLayoutRouting();
    end;

    procedure ApplyInvoiceLayoutRouting()
    begin
        UpsertTenantDefaultReportLayout();
        UpsertCurrentUserReportLayout();
        UpsertGlobalInvoiceReportSelection();
        UpsertDraftInvoiceReportSelection();
        UpsertProFormaInvoiceReportSelection();
        UpdateCustomerInvoiceReportSelections();
    end;

    local procedure UpsertTenantDefaultReportLayout()
    var
        EmptyUserSecurityId: Guid;
    begin
        UpsertTenantReportLayoutSelection(EmptyUserSecurityId);
    end;

    local procedure UpsertCurrentUserReportLayout()
    begin
        UpsertTenantReportLayoutSelection(UserSecurityId());
    end;

    local procedure UpsertTenantReportLayoutSelection(SelectionUserSecurityId: Guid)
    var
        TenantReportLayoutSelection: Record "Tenant Report Layout Selection";
        LayoutAppId: Guid;
    begin
        Evaluate(LayoutAppId, '9f5afdd3-3d75-4660-91c1-91f205680a7d');

        TenantReportLayoutSelection.SetRange("Report ID", Report::FacturaGTM);
        TenantReportLayoutSelection.SetRange("Company Name", CompanyName());
        TenantReportLayoutSelection.SetRange("User ID", SelectionUserSecurityId);

        if not TenantReportLayoutSelection.FindFirst() then begin
            TenantReportLayoutSelection.Init();
            TenantReportLayoutSelection."Report ID" := Report::FacturaGTM;
            TenantReportLayoutSelection."Company Name" := CopyStr(CompanyName(), 1, MaxStrLen(TenantReportLayoutSelection."Company Name"));
            TenantReportLayoutSelection."User ID" := SelectionUserSecurityId;
            TenantReportLayoutSelection.Insert(true);
        end;

        TenantReportLayoutSelection."Layout Name" := LayoutNameLbl;
        TenantReportLayoutSelection."App ID" := LayoutAppId;
        TenantReportLayoutSelection.Modify(true);
    end;

    local procedure UpsertGlobalInvoiceReportSelection()
    var
        ReportSelections: Record "Report Selections";
    begin
        ReportSelections.SetRange(Usage, ReportSelections.Usage::"S.Invoice");
        ReportSelections.SetRange(Sequence, '1');

        if not ReportSelections.FindFirst() then begin
            ReportSelections.Init();
            ReportSelections.Validate(Usage, ReportSelections.Usage::"S.Invoice");
            ReportSelections.Validate(Sequence, '1');
            ReportSelections.Insert(true);
        end;

        ApplySelectionValues(ReportSelections);
        ReportSelections.Modify(true);
    end;

    local procedure UpsertDraftInvoiceReportSelection()
    var
        ReportSelections: Record "Report Selections";
    begin
        UpsertDraftSelection(ReportSelections.Usage::"S.Invoice Draft");
    end;

    local procedure UpsertProFormaInvoiceReportSelection()
    var
        ReportSelections: Record "Report Selections";
    begin
        UpsertDraftSelection(ReportSelections.Usage::"Pro Forma S. Invoice");
    end;

    local procedure UpsertDraftSelection(SelectionUsage: Enum "Report Selection Usage")
    var
        ReportSelections: Record "Report Selections";
    begin
        ReportSelections.SetRange(Usage, SelectionUsage);
        ReportSelections.SetRange(Sequence, '1');

        if not ReportSelections.FindFirst() then begin
            ReportSelections.Init();
            ReportSelections.Validate(Usage, SelectionUsage);
            ReportSelections.Validate(Sequence, '1');
            ReportSelections.Insert(true);
        end;

        ApplyDraftSelectionValues(ReportSelections);
        ReportSelections.Modify(true);
    end;

    local procedure UpdateCustomerInvoiceReportSelections()
    var
        CustomReportSelection: Record "Custom Report Selection";
    begin
        CustomReportSelection.SetFilter(Usage, '%1|%2|%3', CustomReportSelection.Usage::"S.Invoice", CustomReportSelection.Usage::"S.Invoice Draft", CustomReportSelection.Usage::"Pro Forma S. Invoice");

        if not CustomReportSelection.FindSet(true) then
            exit;

        repeat
            if CustomReportSelection.Usage = CustomReportSelection.Usage::"S.Invoice" then
                ApplyCustomSelectionValues(CustomReportSelection)
            else
                ApplyCustomDraftSelectionValues(CustomReportSelection);
            CustomReportSelection.Modify(true);
        until CustomReportSelection.Next() = 0;
    end;

    local procedure ApplySelectionValues(var ReportSelections: Record "Report Selections")
    var
        LayoutAppId: Guid;
    begin
        Evaluate(LayoutAppId, '9f5afdd3-3d75-4660-91c1-91f205680a7d');

        ReportSelections.Validate("Report ID", Report::FacturaGTM);
        ReportSelections.Validate("Use for Email Attachment", true);
        ReportSelections.Validate("Use for Email Body", false);
        ReportSelections."Report Layout Name" := LayoutNameLbl;
        ReportSelections."Report Layout AppID" := LayoutAppId;
        ReportSelections."Report Layout Caption" := LayoutCaptionLbl;
        ReportSelections."Report Layout Publisher" := 'MTM Logix';
    end;

    local procedure ApplyDraftSelectionValues(var ReportSelections: Record "Report Selections")
    var
        LayoutAppId: Guid;
    begin
        Evaluate(LayoutAppId, '9f5afdd3-3d75-4660-91c1-91f205680a7d');

        ReportSelections.Validate("Report ID", Report::"MTM GT Draft Invoice");
        ReportSelections.Validate("Use for Email Attachment", true);
        ReportSelections.Validate("Use for Email Body", false);
        ReportSelections."Report Layout Name" := LayoutNameLbl;
        ReportSelections."Report Layout AppID" := LayoutAppId;
        ReportSelections."Report Layout Caption" := LayoutCaptionLbl;
        ReportSelections."Report Layout Publisher" := 'MTM Logix';
    end;

    local procedure ApplyCustomSelectionValues(var CustomReportSelection: Record "Custom Report Selection")
    var
        LayoutAppId: Guid;
    begin
        Evaluate(LayoutAppId, '9f5afdd3-3d75-4660-91c1-91f205680a7d');

        CustomReportSelection.Validate("Report ID", Report::FacturaGTM);
        CustomReportSelection.Validate("Use for Email Attachment", true);
        CustomReportSelection.Validate("Use for Email Body", false);
        CustomReportSelection."Email Attachment Layout Name" := LayoutNameLbl;
        CustomReportSelection."Email Attachment Layout AppID" := LayoutAppId;
    end;

    local procedure ApplyCustomDraftSelectionValues(var CustomReportSelection: Record "Custom Report Selection")
    var
        LayoutAppId: Guid;
    begin
        Evaluate(LayoutAppId, '9f5afdd3-3d75-4660-91c1-91f205680a7d');

        CustomReportSelection.Validate("Report ID", Report::"MTM GT Draft Invoice");
        CustomReportSelection.Validate("Use for Email Attachment", true);
        CustomReportSelection.Validate("Use for Email Body", false);
        CustomReportSelection."Email Attachment Layout Name" := LayoutNameLbl;
        CustomReportSelection."Email Attachment Layout AppID" := LayoutAppId;
    end;
}
