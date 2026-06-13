page 71005 "MTM Doc Sending Profiles API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'layoutAudit';
    APIVersion = 'v1.0';
    EntityName = 'documentSendingProfile';
    EntitySetName = 'documentSendingProfiles';
    SourceTable = "Document Sending Profile";
    ODataKeyFields = SystemId;
    DelayedInsert = false;
    Extensible = false;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;
    Permissions = tabledata "Document Sending Profile" = r;

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
                field(code; Rec.Code)
                {
                    Caption = 'Code';
                }
                field(description; Rec.Description)
                {
                    Caption = 'Description';
                }
                field(printer; PrinterTxt)
                {
                    Caption = 'Printer';
                }
                field(email; EmailTxt)
                {
                    Caption = 'E-Mail';
                }
                field(emailAttachment; EmailAttachmentTxt)
                {
                    Caption = 'E-Mail Attachment';
                }
                field(emailFormat; Rec."E-Mail Format")
                {
                    Caption = 'E-Mail Format';
                }
                field(disk; DiskTxt)
                {
                    Caption = 'Disk';
                }
                field(diskFormat; Rec."Disk Format")
                {
                    Caption = 'Disk Format';
                }
                field(electronicDocument; ElectronicDocumentTxt)
                {
                    Caption = 'Electronic Document';
                }
                field(electronicFormat; Rec."Electronic Format")
                {
                    Caption = 'Electronic Format';
                }
                field(isDefault; Rec.Default)
                {
                    Caption = 'Default';
                }
                field(sendTo; SendToTxt)
                {
                    Caption = 'Send To';
                }
                field(usage; UsageTxt)
                {
                    Caption = 'Usage';
                }
                field(oneRelatedPartySelected; Rec."One Related Party Selected")
                {
                    Caption = 'One Related Party Selected';
                }
                field(combineEmailDocuments; Rec."Combine Email Documents")
                {
                    Caption = 'Combine Email Documents';
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
        PrinterTxt := Format(Rec.Printer);
        EmailTxt := Format(Rec."E-Mail");
        EmailAttachmentTxt := Format(Rec."E-Mail Attachment");
        DiskTxt := Format(Rec.Disk);
        ElectronicDocumentTxt := Format(Rec."Electronic Document");
        SendToTxt := Format(Rec."Send To");
        UsageTxt := Format(Rec.Usage);
    end;

    var
        PrinterTxt: Text[100];
        EmailTxt: Text[100];
        EmailAttachmentTxt: Text[100];
        DiskTxt: Text[100];
        ElectronicDocumentTxt: Text[100];
        SendToTxt: Text[100];
        UsageTxt: Text[100];
}
