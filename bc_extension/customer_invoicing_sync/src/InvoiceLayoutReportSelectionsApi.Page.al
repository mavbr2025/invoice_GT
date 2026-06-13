page 71001 "MTM Report Selections API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'layoutAudit';
    APIVersion = 'v1.0';
    EntityName = 'reportSelection';
    EntitySetName = 'reportSelections';
    SourceTable = "Report Selections";
    ODataKeyFields = SystemId;
    DelayedInsert = false;
    Extensible = false;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;
    Permissions = tabledata "Report Selections" = r;

    layout
    {
        area(Content)
        {
            repeater(General)
            {
                field(id; Rec.SystemId)
                {
                    Caption = 'Id';
                }
                field(usage; UsageTxt)
                {
                    Caption = 'Usage';
                }
                field(sequence; Rec.Sequence)
                {
                    Caption = 'Sequence';
                }
                field(reportId; Rec."Report ID")
                {
                    Caption = 'Report ID';
                }
                field(reportCaption; Rec."Report Caption")
                {
                    Caption = 'Report Caption';
                }
                field(customReportLayoutCode; Rec."Custom Report Layout Code")
                {
                    Caption = 'Custom Report Layout Code';
                }
                field(useForEmailAttachment; Rec."Use for Email Attachment")
                {
                    Caption = 'Use for Email Attachment';
                }
                field(useForEmailBody; Rec."Use for Email Body")
                {
                    Caption = 'Use for Email Body';
                }
                field(emailBodyLayoutCode; Rec."Email Body Layout Code")
                {
                    Caption = 'Email Body Layout Code';
                }
                field(emailBodyLayoutDescription; Rec."Email Body Layout Description")
                {
                    Caption = 'Email Body Layout Description';
                }
                field(emailBodyLayoutType; EmailBodyLayoutTypeTxt)
                {
                    Caption = 'Email Body Layout Type';
                }
                field(emailBodyLayoutName; Rec."Email Body Layout Name")
                {
                    Caption = 'Email Body Layout Name';
                }
                field(emailBodyLayoutAppId; Rec."Email Body Layout AppID")
                {
                    Caption = 'Email Body Layout App ID';
                }
                field(emailBodyLayoutPublisher; Rec."Email Body Layout Publisher")
                {
                    Caption = 'Email Body Layout Publisher';
                }
                field(emailBodyLayoutCaption; Rec."Email Body Layout Caption")
                {
                    Caption = 'Email Body Layout Caption';
                }
                field(reportLayoutName; Rec."Report Layout Name")
                {
                    Caption = 'Report Layout Name';
                }
                field(reportLayoutAppId; Rec."Report Layout AppID")
                {
                    Caption = 'Report Layout App ID';
                }
                field(reportLayoutCaption; Rec."Report Layout Caption")
                {
                    Caption = 'Report Layout Caption';
                }
                field(reportLayoutPublisher; Rec."Report Layout Publisher")
                {
                    Caption = 'Report Layout Publisher';
                }
                field(systemModifiedAt; Rec.SystemModifiedAt)
                {
                    Caption = 'System Modified At';
                }
            }
        }
    }

    trigger OnAfterGetRecord()
    begin
        UsageTxt := Format(Rec.Usage);
        EmailBodyLayoutTypeTxt := Format(Rec."Email Body Layout Type");
    end;

    var
        UsageTxt: Text[100];
        EmailBodyLayoutTypeTxt: Text[100];
}

