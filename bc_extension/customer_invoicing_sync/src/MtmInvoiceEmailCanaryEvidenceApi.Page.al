page 71013 "MTM Inv Email Canary Ev API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'invoiceSync';
    APIVersion = 'v1.0';
    EntityName = 'invoiceEmailCanaryEvidence';
    EntitySetName = 'invoiceEmailCanaryEvidenceEntries';
    SourceTable = "Sales Invoice Header";
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
                    Editable = false;
                }
                field(number; Rec."No.")
                {
                    Caption = 'Number';
                    Editable = false;
                }
                field(evidence; GetInternalCanaryEmailEvidence())
                {
                    Caption = 'Evidence';
                    Editable = false;
                }
            }
        }
    }

    local procedure GetInternalCanaryEmailEvidence(): Text
    var
        InvoiceCustomerEmailMgt: Codeunit "MTM Invoice Customer Email Mgt";
    begin
        exit(InvoiceCustomerEmailMgt.GetApprovedInvoiceTestEmailEvidence(Rec));
    end;
}
