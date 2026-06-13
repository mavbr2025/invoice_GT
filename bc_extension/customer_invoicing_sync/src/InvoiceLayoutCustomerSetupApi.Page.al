page 71006 "MTM Customer Layout Setup API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'layoutAudit';
    APIVersion = 'v1.0';
    EntityName = 'customerLayoutSetup';
    EntitySetName = 'customerLayoutSetup';
    SourceTable = Customer;
    ODataKeyFields = SystemId;
    DelayedInsert = false;
    Extensible = false;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;
    Permissions = tabledata Customer = r;

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
                field(number; Rec."No.")
                {
                    Caption = 'Number';
                }
                field(displayName; Rec.Name)
                {
                    Caption = 'Display Name';
                }
                field(vatRegistrationNumber; Rec."VAT Registration No.")
                {
                    Caption = 'VAT Registration Number';
                }
                field(email; Rec."E-Mail")
                {
                    Caption = 'Email';
                }
                field(documentSendingProfile; Rec."Document Sending Profile")
                {
                    Caption = 'Document Sending Profile';
                }
                field(systemModifiedAt; Rec.SystemModifiedAt)
                {
                    Caption = 'System Modified At';
                }
            }
        }
    }
}

