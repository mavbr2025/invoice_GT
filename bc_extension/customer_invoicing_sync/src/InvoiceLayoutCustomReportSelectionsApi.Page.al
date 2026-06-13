page 71002 "MTM Custom Report Sel API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'layoutAudit';
    APIVersion = 'v1.0';
    EntityName = 'customReportSelection';
    EntitySetName = 'customReportSelections';
    SourceTable = "Custom Report Selection";
    ODataKeyFields = SystemId;
    DelayedInsert = false;
    Extensible = false;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;
    Permissions = tabledata "Custom Report Selection" = r;

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
                field(sourceType; Rec."Source Type")
                {
                    Caption = 'Source Type';
                }
                field(sourceNo; Rec."Source No.")
                {
                    Caption = 'Source No.';
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
                field(customReportDescription; Rec."Custom Report Description")
                {
                    Caption = 'Custom Report Description';
                }
                field(sendToEmail; Rec."Send To Email")
                {
                    Caption = 'Send To Email';
                }
                field(useForEmailAttachment; Rec."Use for Email Attachment")
                {
                    Caption = 'Use for Email Attachment';
                }
                field(useForEmailBody; Rec."Use for Email Body")
                {
                    Caption = 'Use for Email Body';
                }
                field(emailAttachmentLayoutName; Rec."Email Attachment Layout Name")
                {
                    Caption = 'Email Attachment Layout Name';
                }
                field(emailAttachmentLayoutAppId; Rec."Email Attachment Layout AppID")
                {
                    Caption = 'Email Attachment Layout App ID';
                }
                field(emailBodyLayoutCode; Rec."Email Body Layout Code")
                {
                    Caption = 'Email Body Layout Code';
                }
                field(emailBodyLayoutDescription; Rec."Email Body Layout Description")
                {
                    Caption = 'Email Body Layout Description';
                }
                field(emailBodyLayoutName; Rec."Email Body Layout Name")
                {
                    Caption = 'Email Body Layout Name';
                }
                field(emailBodyLayoutAppId; Rec."Email Body Layout AppID")
                {
                    Caption = 'Email Body Layout App ID';
                }
                field(emailBodyLayoutCaption; Rec."Email Body Layout Caption")
                {
                    Caption = 'Email Body Layout Caption';
                }
                field(useEmailFromContact; Rec."Use Email from Contact")
                {
                    Caption = 'Use Email from Contact';
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
    end;

    var
        UsageTxt: Text[100];
}

