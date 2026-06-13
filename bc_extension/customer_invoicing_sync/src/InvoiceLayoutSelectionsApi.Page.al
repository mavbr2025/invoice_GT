page 71003 "MTM Report Layout Sel API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'layoutAudit';
    APIVersion = 'v1.0';
    EntityName = 'reportLayoutSelection';
    EntitySetName = 'reportLayoutSelections';
    SourceTable = "Report Layout Selection";
    ODataKeyFields = SystemId;
    DelayedInsert = false;
    Extensible = false;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;
    Permissions = tabledata "Report Layout Selection" = r;

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
                field(reportId; Rec."Report ID")
                {
                    Caption = 'Report ID';
                }
                field(reportName; Rec."Report Name")
                {
                    Caption = 'Report Name';
                }
                field(companyName; Rec."Company Name")
                {
                    Caption = 'Company Name';
                }
                field(type; TypeTxt)
                {
                    Caption = 'Type';
                }
                field(customReportLayoutCode; Rec."Custom Report Layout Code")
                {
                    Caption = 'Custom Report Layout Code';
                }
                field(reportLayoutDescription; Rec."Report Layout Description")
                {
                    Caption = 'Report Layout Description';
                }
                field(reportCaption; Rec."Report Caption")
                {
                    Caption = 'Report Caption';
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
        TypeTxt := Format(Rec.Type);
    end;

    var
        TypeTxt: Text[100];
}

