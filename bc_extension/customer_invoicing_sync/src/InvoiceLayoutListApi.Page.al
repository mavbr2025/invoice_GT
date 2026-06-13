page 71004 "MTM Report Layout List API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'layoutAudit';
    APIVersion = 'v1.0';
    EntityName = 'reportLayout';
    EntitySetName = 'reportLayouts';
    SourceTable = "Report Layout List";
    ODataKeyFields = SystemId;
    DelayedInsert = false;
    Extensible = false;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;

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
                field(name; Rec.Name)
                {
                    Caption = 'Name';
                }
                field(caption; Rec.Caption)
                {
                    Caption = 'Caption';
                }
                field(reportName; Rec."Report Name")
                {
                    Caption = 'Report Name';
                }
                field(layoutFormat; LayoutFormatTxt)
                {
                    Caption = 'Layout Format';
                }
                field(mimeType; Rec."MIME Type")
                {
                    Caption = 'MIME Type';
                }
                field(description; Rec.Description)
                {
                    Caption = 'Description';
                }
                field(applicationId; Rec."Application ID")
                {
                    Caption = 'Application ID';
                }
                field(layoutPublisher; Rec."Layout Publisher")
                {
                    Caption = 'Layout Publisher';
                }
                field(userDefined; Rec."User Defined")
                {
                    Caption = 'User Defined';
                }
                field(reportIsInstalled; Rec.ReportIsInstalled)
                {
                    Caption = 'Report Is Installed';
                }
                field(isObsolete; Rec.IsObsolete)
                {
                    Caption = 'Is Obsolete';
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
        LayoutFormatTxt := Format(Rec."Layout Format");
    end;

    var
        LayoutFormatTxt: Text[100];
}

